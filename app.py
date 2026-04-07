import sys
import requests
import MarketplaceScraper
import os
import json
import datetime
import hashlib
import shutil
import re
import time
from queue import Queue, Empty

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QTextEdit, QSplitter, QMessageBox, QProgressBar, QComboBox,
    QDialog, QCheckBox, QFrame, QSizePolicy
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QFont, QPainter


def get_image_cache_path(url):
    cache_dir = "cache/images"
    os.makedirs(cache_dir, exist_ok=True)
    filename = hashlib.md5(url.encode()).hexdigest() + ".jpg"
    return os.path.join(cache_dir, filename)

def clear_cache_directory():
    if os.path.exists("cache"):
        shutil.rmtree("cache", ignore_errors=True)
    os.makedirs("cache/images", exist_ok=True)

def parse_price(price_str):
    if not price_str: return 0.0
    clean = re.sub(r'[^\d.]', '', str(price_str))
    try: return float(clean) if clean else 0.0
    except: return 0.0

def get_condition_score(cond_str):
    c = str(cond_str).lower()
    if "new" in c and "like" not in c: return 5
    if "like new" in c: return 4
    if "good" in c: return 3
    if "fair" in c: return 2
    if "used" in c: return 1
    return 0


class ImageLabel(QWidget):
    clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #eee; border: 1px solid #ccc;")
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pixmap = None
        self._text = ""

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self._text = ""
        self.update()

    def setText(self, text):
        self._pixmap = None
        self._text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap and not self._pixmap.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        elif self._text:
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(self.rect(), Qt.AlignCenter, self._text)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FullScreenViewer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowFullScreen)
        self.setStyleSheet("background-color: black; color: white;")
        
        self._pixmap = None
        self._text = "Loading..."

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self._text = ""
        self.update()

    def set_text(self, text):
        self._pixmap = None
        self._text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap and not self._pixmap.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        elif self._text:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, self._text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            if self.parent(): self.parent().prev_image()
        elif event.key() == Qt.Key_Right:
            if self.parent(): self.parent().next_image()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.close()


class CollapsibleBox(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.base_title = title
        self.toggle_btn = QPushButton(f"▶ {self.base_title}")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setStyleSheet("text-align: left; font-weight: bold; padding: 6px; background-color: #e0e0e0; border: 1px solid #ccc; border-radius: 3px;")
        self.toggle_btn.clicked.connect(self.on_toggle)
        
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_area.setVisible(False)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 5)
        layout.setSpacing(0)
        layout.addWidget(self.toggle_btn)
        layout.addWidget(self.content_area)
        
    def on_toggle(self, checked):
        self.toggle_btn.setText(f"▼ {self.base_title}" if checked else f"▶ {self.base_title}")
        self.content_area.setVisible(checked)
        
    def expand(self):
        if not self.toggle_btn.isChecked():
            self.toggle_btn.setChecked(True)
            self.on_toggle(True)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(400, 320)
        
        layout = QVBoxLayout(self)
        
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("Proxy: http://user:pass@host:port")
        layout.addWidget(QLabel("Proxy Configuration:"))
        layout.addWidget(self.proxy_input)

        self.pages_input = QLineEdit()
        self.pages_input.setPlaceholderText("Number of pages per load (default: 1)")
        layout.addWidget(QLabel("Pages per load (24 items per page):"))
        layout.addWidget(self.pages_input)
        
        self.bg_desc_cb = QCheckBox("Fetch descriptions in background")
        self.bg_img_cb = QCheckBox("Fetch images in background (High Ban Risk)")
        layout.addWidget(self.bg_desc_cb)
        layout.addWidget(self.bg_img_cb)

        self.rate_limit_input = QLineEdit()
        self.rate_limit_input.setPlaceholderText("Seconds between requests (e.g. 2.0)")
        layout.addWidget(QLabel("Background Rate Limit (Seconds):"))
        layout.addWidget(self.rate_limit_input)
        
        self.auto_clear_cb = QCheckBox("Automatically clear cache on startup")
        layout.addWidget(self.auto_clear_cb)
        
        self.clear_btn = QPushButton("Clear Cache Now")
        self.clear_btn.clicked.connect(self.manual_clear)
        layout.addWidget(self.clear_btn)
        
        layout.addStretch()
        
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.accept)
        layout.addWidget(self.save_btn)

    def manual_clear(self):
        clear_cache_directory()
        QMessageBox.information(self, "Cache Cleared", "Cache directory has been wiped.")


class WishlistPopup(QWidget):
    updated = pyqtSignal(str)

    def __init__(self, existing_wishlists, current_wishlist="Default", parent=None):
        # Using Qt.Popup creates an inline popup that vanishes when clicking away
        super().__init__(parent, Qt.Popup)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            WishlistPopup {
                background-color: white; 
                border: 1px solid #999; 
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        layout.addWidget(QLabel("<b>Saved!</b> Select wishlist:"))
        
        self.combo = QComboBox()
        wls = list(existing_wishlists)
        if "Default" in wls: 
            wls.remove("Default")
        wls = ["Default"] + sorted(wls)
        self.combo.addItems(wls)
        self.combo.setCurrentText(current_wishlist)
        
        self.new_input = QLineEdit()
        self.new_input.setPlaceholderText("Or create new...")
        
        btn = QPushButton("Update Wishlist")
        btn.clicked.connect(self.on_submit)
        
        layout.addWidget(self.combo)
        layout.addWidget(self.new_input)
        layout.addWidget(btn)
        
    def on_submit(self):
        new_wl = self.new_input.text().strip()
        if new_wl:
            self.updated.emit(new_wl)
        else:
            self.updated.emit(self.combo.currentText())
        self.close()


class ConditionWidget(QWidget):
    changed = pyqtSignal()
    removed = pyqtSignal(QWidget)

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "Title", "Description", "Attributes"])

        self.cond_combo = QComboBox()
        self.cond_combo.addItems(["Must Contain", "Must NOT Contain", "Exact Text", "Any of this text"])

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Value (comma separated for 'Any of')...")

        self.remove_btn = QPushButton("X")
        self.remove_btn.setFixedWidth(30)

        layout.addWidget(self.type_combo)
        layout.addWidget(self.cond_combo)
        layout.addWidget(self.text_input)
        layout.addWidget(self.remove_btn)

        self.type_combo.currentIndexChanged.connect(lambda: self.changed.emit())
        self.cond_combo.currentIndexChanged.connect(lambda: self.changed.emit())
        self.text_input.textChanged.connect(lambda: self.changed.emit())
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        
    def evaluate(self, title, desc, attrs):
        f_type = self.type_combo.currentText()
        cond = self.cond_combo.currentText()
        val = self.text_input.text().strip().lower()
        
        if not val: return True
            
        if f_type == "Title": field_val = title
        elif f_type == "Description": field_val = desc
        elif f_type == "Attributes": field_val = attrs
        else: field_val = f"{title} {desc} {attrs}"
        
        if cond == "Must Contain": return val in field_val
        elif cond == "Must NOT Contain": return val not in field_val
        elif cond == "Exact Text": return val == field_val
        elif cond == "Any of this text":
            parts = [p.strip() for p in val.split(',')]
            return any(p in field_val for p in parts if p)
        return False


class SortTierWidget(QFrame):
    changed = pyqtSignal()
    removed = pyqtSignal(QWidget)
    move_up = pyqtSignal(QWidget)
    move_down = pyqtSignal(QWidget)

    def __init__(self):
        super().__init__()
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        
        top_layout = QHBoxLayout()
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Price", "Time Listed", "Distance", "Item Condition", "Conditions Matched"])
        
        self.dir_combo = QComboBox()
        self.dir_combo.addItems(["Ascending", "Descending"])
        
        self.up_btn = QPushButton("↑")
        self.up_btn.setFixedWidth(30)
        self.down_btn = QPushButton("↓")
        self.down_btn.setFixedWidth(30)
        self.remove_btn = QPushButton("X")
        self.remove_btn.setFixedWidth(30)
        
        top_layout.addWidget(QLabel("Sort By:"))
        top_layout.addWidget(self.type_combo)
        top_layout.addWidget(self.dir_combo)
        top_layout.addWidget(self.up_btn)
        top_layout.addWidget(self.down_btn)
        top_layout.addWidget(self.remove_btn)
        
        self.main_layout.addLayout(top_layout)
        
        self.conditions_container = QWidget()
        self.conditions_layout = QVBoxLayout(self.conditions_container)
        self.conditions_layout.setContentsMargins(0, 5, 0, 0)
        
        self.add_cond_btn = QPushButton("Add Match Condition")
        self.conditions_layout.addWidget(self.add_cond_btn)
        
        self.main_layout.addWidget(self.conditions_container)
        self.conditions_container.setVisible(False)
        
        self.conditions = []
        
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        self.dir_combo.currentIndexChanged.connect(lambda: self.changed.emit())
        self.up_btn.clicked.connect(lambda: self.move_up.emit(self))
        self.down_btn.clicked.connect(lambda: self.move_down.emit(self))
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        self.add_cond_btn.clicked.connect(self.add_condition)

    def on_type_changed(self):
        is_cond = self.type_combo.currentText() == "Conditions Matched"
        self.conditions_container.setVisible(is_cond)
        self.changed.emit()

    def add_condition(self):
        w = ConditionWidget()
        w.changed.connect(self.changed.emit)
        w.removed.connect(self.remove_condition)
        self.conditions_layout.insertWidget(self.conditions_layout.count() - 1, w)
        self.conditions.append(w)
        self.changed.emit()

    def remove_condition(self, w):
        self.conditions_layout.removeWidget(w)
        w.deleteLater()
        self.conditions.remove(w)
        self.changed.emit()


class ListingItemWidget(QWidget):
    fav_clicked = pyqtSignal(bool, QWidget) # Emits True/False and the button widget reference
    
    def __init__(self, title, price, is_fav=False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        top_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"<b>{title}</b><br>{price}")
        self.title_lbl.setWordWrap(True)
        
        self.fav_btn = QPushButton("❤" if is_fav else "♡")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setChecked(is_fav)
        self.fav_btn.setFixedSize(30, 30)
        self.fav_btn.setStyleSheet("color: red; font-weight: bold; font-size: 16px; border: none; background: transparent;")
        self.fav_btn.clicked.connect(self.toggle_fav)
        
        top_layout.addWidget(self.title_lbl)
        top_layout.addWidget(self.fav_btn)
        
        self.thumb_lbl = QLabel("Loading thumbnail...")
        self.thumb_lbl.setFixedSize(140, 140)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet("background-color: #eee; border: 1px solid #ccc;")
        
        layout.addLayout(top_layout)
        layout.addWidget(self.thumb_lbl)
        
    def toggle_fav(self):
        checked = self.fav_btn.isChecked()
        self.fav_btn.setText("❤" if checked else "♡")
        self.fav_clicked.emit(checked, self.fav_btn)
        
    def set_thumbnail(self, pixmap):
        self.thumb_lbl.setPixmap(pixmap.scaled(self.thumb_lbl.width(), self.thumb_lbl.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.thumb_lbl.setText("")


class CustomListWidgetItem(QListWidgetItem):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        
    def __lt__(self, other):
        return self.main_app.compare_items(self, other)


class SearchWorker(QThread):
    finished = pyqtSignal(list, str, str, bool, str, str)
    def __init__(self, location, query, pages=1, min_price=None, max_price=None, cursor=None, lat=None, lng=None):
        super().__init__()
        self.location, self.query, self.pages, self.min_price, self.max_price = location, query, pages, min_price, max_price
        self.cursor = cursor
        self.lat = lat
        self.lng = lng
        
    def run(self):
        if not self.lat or not self.lng:
            status, error, loc_data = MarketplaceScraper.getLocations(self.location)
            if (status != "Success" or not loc_data.get("locations")) and "," in self.location:
                status, error, loc_data = MarketplaceScraper.getLocations(self.location.split(",")[0].strip())

            if status != "Success" or not loc_data.get("locations"):
                self.finished.emit([], f"Could not find location. Error: {error.get('message', 'No matches found.')}", None, False, None, None)
                return
                
            self.lat, self.lng = loc_data["locations"][0]["latitude"], loc_data["locations"][0]["longitude"]
            
        status, error, list_data = MarketplaceScraper.getListings(
            self.lat, self.lng, self.query, numPageResults=self.pages, 
            minPrice=self.min_price, maxPrice=self.max_price, cursor=self.cursor
        )
        if status != "Success":
            self.finished.emit([], f"Error fetching listings: {error.get('message')}", None, False, self.lat, self.lng)
            return
            
        all_listings = []
        for page in list_data.get("listingPages", []):
            all_listings.extend(page.get("listings", []))
            
        page_info = list_data.get("page_info", {})
        self.finished.emit(all_listings, "", page_info.get("end_cursor"), page_info.get("has_next_page", False), self.lat, self.lng)


class ThumbnailWorker(QThread):
    thumbnail_fetched = pyqtSignal(str, bytes)
    
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.running = True
        
    def add_items(self, listings):
        for item in listings:
            if item.get("primaryPhotoURL"):
                self.queue.put((item["id"], item["primaryPhotoURL"]))
                
    def run(self):
        while self.running:
            try:
                item_id, url = self.queue.get(timeout=0.5)
            except Empty:
                continue
                
            if not self.running: break
            try:
                cache_path = get_image_cache_path(url)
                if os.path.exists(cache_path):
                    with open(cache_path, "rb") as f: data = f.read()
                    self.thumbnail_fetched.emit(item_id, data)
                    continue
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    with open(cache_path, "wb") as f: f.write(res.content)
                    self.thumbnail_fetched.emit(item_id, res.content)
            except: pass
            
    def stop(self): self.running = False


class BackgroundWorker(QThread):
    details_fetched = pyqtSignal(str, dict)
    
    def __init__(self, fetch_desc=False, fetch_images=False, delay=2.0):
        super().__init__()
        self.fetch_desc = fetch_desc
        self.fetch_images = fetch_images
        self.delay = delay
        self.queue = Queue()
        self.running = True
        
    def add_item(self, item_id):
        self.queue.put(item_id)
        
    def clear_queue(self):
        with self.queue.mutex:
            self.queue.queue.clear()
        
    def run(self):
        while self.running:
            try:
                item_id = self.queue.get(timeout=0.5)
            except Empty:
                continue
                
            if not self.running: break
            
            if not self.fetch_desc and not self.fetch_images:
                self.clear_queue()
                continue
                
            data = {}
            if self.fetch_desc:
                status, error, desc_data = MarketplaceScraper.getListingDetails(item_id)
                if status == "Success":
                    data.update(desc_data)
                else:
                    data["description"] = f"Error: {error.get('message')}"
            
            if self.fetch_images:
                img_status, img_error, img_urls = MarketplaceScraper.getListingImages(item_id)
                data["image_urls"] = img_urls if img_status == "Success" else []
            else:
                data["image_urls"] = None
                
            self.details_fetched.emit(item_id, data)
            time.sleep(self.delay)
            
    def stop(self):
        self.running = False


class OnDemandWorker(QThread):
    details_fetched = pyqtSignal(str, dict)
    
    def __init__(self, item_id, fetch_desc, fetch_images):
        super().__init__()
        self.item_id = item_id
        self.fetch_desc = fetch_desc
        self.fetch_images = fetch_images
        
    def run(self):
        data = {}
        if self.fetch_desc:
            status, error, desc_data = MarketplaceScraper.getListingDetails(self.item_id)
            if status == "Success":
                data.update(desc_data)
            else:
                data["description"] = f"Error: {error.get('message')}"
                
        if self.fetch_images:
            img_status, img_error, img_urls = MarketplaceScraper.getListingImages(self.item_id)
            data["image_urls"] = img_urls if img_status == "Success" else []
            
        self.details_fetched.emit(self.item_id, data)


class ImageWorker(QThread):
    image_fetched = pyqtSignal(str, bytes)
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            cache_path = get_image_cache_path(self.url)
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as f: data = f.read()
                self.image_fetched.emit(self.url, data)
                return
            res = requests.get(self.url, timeout=5)
            if res.status_code == 200:
                with open(cache_path, "wb") as f: f.write(res.content)
                self.image_fetched.emit(self.url, res.content)
        except: pass


class MarketplaceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Facebook Marketplace Browser")
        self.resize(1300, 850)
        
        self.listings = []
        self.favorites = {}
        self.in_favorites_view = False
        
        self.listing_details = {}
        self.image_cache = {} 
        self.filter_conditions = []
        self.sort_tiers = []
        
        self.current_cursor = None
        self.has_next_page = False
        self.is_loading_more = False
        self.current_lat = None
        self.current_lng = None
        
        self.current_loc = ""
        self.current_query = ""
        self.current_min_price = ""
        self.current_max_price = ""
        
        self.current_item = None
        self.current_item_images = []
        self.current_image_index = 0
        self.wishlist_popup = None
        
        self.search_worker = None
        self.image_workers = []
        self.ondemand_workers = []
        
        self.fullscreen_viewer = FullScreenViewer(self)
        
        self.loading_settings = True
        self.init_settings()
        
        self.thumb_worker = ThumbnailWorker()
        self.thumb_worker.thumbnail_fetched.connect(self.on_thumbnail_fetched)
        self.thumb_worker.start()
        
        self.bg_worker = BackgroundWorker(
            fetch_desc=self.settings.get("bg_descriptions", False),
            fetch_images=self.settings.get("bg_images", False),
            delay=self.settings.get("bg_rate_limit", 2.0)
        )
        self.bg_worker.details_fetched.connect(self.on_background_fetched)
        self.bg_worker.start()
        
        self.load_favorites()
        self.init_ui()
        self.load_filters_and_sorts()
        
    def init_settings(self):
        self.settings = {
            "proxy": "", 
            "auto_clear": False,
            "pages_per_load": 1,
            "bg_descriptions": False,
            "bg_images": False,
            "bg_rate_limit": 2.0,
            "filters": [], 
            "sorts": [],
            "location": "Sydney, NSW, Australia",
            "query": "cloud couch",
            "min_price": "",
            "max_price": ""
        }
        if os.path.exists("settings.json"):
            try:
                with open("settings.json", "r") as f:
                    self.settings.update(json.load(f))
            except: pass
            
        if self.settings.get("auto_clear"):
            clear_cache_directory()
        else:
            os.makedirs("cache/images", exist_ok=True)
            
        self.apply_proxy()

    def load_favorites(self):
        self.favorites.clear()
        if os.path.exists("save.json"):
            try:
                with open("save.json", "r") as f:
                    data = json.load(f)
                    for item in data:
                        self.favorites[item["id"]] = item
            except Exception as e:
                print("Failed to load favorites:", e)
                
    def save_favorites(self):
        try:
            with open("save.json", "w") as f:
                json.dump(list(self.favorites.values()), f, indent=4)
        except Exception as e:
            print("Failed to save favorites:", e)

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.proxy_input.setText(self.settings.get("proxy", ""))
        dlg.auto_clear_cb.setChecked(self.settings.get("auto_clear", False))
        dlg.pages_input.setText(str(self.settings.get("pages_per_load", 1)))
        dlg.bg_desc_cb.setChecked(self.settings.get("bg_descriptions", False))
        dlg.bg_img_cb.setChecked(self.settings.get("bg_images", False))
        dlg.rate_limit_input.setText(str(self.settings.get("bg_rate_limit", 2.0)))
        
        if dlg.exec_():
            self.settings["proxy"] = dlg.proxy_input.text().strip()
            self.settings["auto_clear"] = dlg.auto_clear_cb.isChecked()
            self.settings["bg_descriptions"] = dlg.bg_desc_cb.isChecked()
            self.settings["bg_images"] = dlg.bg_img_cb.isChecked()
            try:
                self.settings["pages_per_load"] = int(dlg.pages_input.text().strip())
            except ValueError:
                self.settings["pages_per_load"] = 1
            try:
                self.settings["bg_rate_limit"] = float(dlg.rate_limit_input.text().strip())
            except ValueError:
                self.settings["bg_rate_limit"] = 2.0
                
            self.save_to_disk()
            self.apply_proxy()
            
            self.bg_worker.fetch_desc = self.settings["bg_descriptions"]
            self.bg_worker.fetch_images = self.settings["bg_images"]
            self.bg_worker.delay = self.settings["bg_rate_limit"]
            if not self.settings["bg_descriptions"] and not self.settings["bg_images"]:
                self.bg_worker.clear_queue()

    def apply_proxy(self):
        proxy_str = self.settings.get("proxy", "")
        if proxy_str:
            if "://" not in proxy_str: proxy_str = f"http://{proxy_str}"
            MarketplaceScraper.PROXY_CONFIG = {"http": proxy_str, "https": proxy_str}
        else:
            MarketplaceScraper.PROXY_CONFIG = {}

    def save_current_settings(self):
        if self.loading_settings: return
        
        self.settings["location"] = self.loc_input.text()
        self.settings["query"] = self.query_input.text()
        self.settings["min_price"] = self.min_price_input.text()
        self.settings["max_price"] = self.max_price_input.text()
        
        f_data = []
        for fw in self.filter_conditions:
            f_data.append({
                "type": fw.type_combo.currentText(),
                "cond": fw.cond_combo.currentText(),
                "val": fw.text_input.text()
            })
            
        s_data = []
        for sw in self.sort_tiers:
            c_data = []
            for cw in sw.conditions:
                c_data.append({
                    "type": cw.type_combo.currentText(),
                    "cond": cw.cond_combo.currentText(),
                    "val": cw.text_input.text()
                })
            s_data.append({
                "type": sw.type_combo.currentText(),
                "dir": sw.dir_combo.currentText(),
                "conditions": c_data
            })
            
        self.settings["filters"] = f_data
        self.settings["sorts"] = s_data
        self.save_to_disk()

    def save_to_disk(self):
        with open("settings.json", "w") as f:
            json.dump(self.settings, f, indent=4)

    def load_filters_and_sorts(self):
        self.loading_settings = True
        
        for fd in self.settings.get("filters", []):
            fw = ConditionWidget()
            fw.type_combo.setCurrentText(fd.get("type", "All"))
            fw.cond_combo.setCurrentText(fd.get("cond", "Must Contain"))
            fw.text_input.setText(fd.get("val", ""))
            
            fw.changed.connect(self.on_filter_sort_changed)
            fw.removed.connect(self.remove_filter_condition)
            self.filter_box.content_layout.insertWidget(self.filter_box.content_layout.count() - 1, fw)
            self.filter_conditions.append(fw)
            
        for sd in self.settings.get("sorts", []):
            sw = SortTierWidget()
            sw.type_combo.setCurrentText(sd.get("type", "Price"))
            sw.dir_combo.setCurrentText(sd.get("dir", "Ascending"))
            
            for cd in sd.get("conditions", []):
                cw = ConditionWidget()
                cw.type_combo.setCurrentText(cd.get("type", "All"))
                cw.cond_combo.setCurrentText(cd.get("cond", "Must Contain"))
                cw.text_input.setText(cd.get("val", ""))
                
                cw.changed.connect(sw.changed.emit)
                cw.removed.connect(sw.remove_condition)
                sw.conditions_layout.insertWidget(sw.conditions_layout.count() - 1, cw)
                sw.conditions.append(cw)
                
            sw.changed.connect(self.on_filter_sort_changed)
            sw.removed.connect(self.remove_sort_tier)
            sw.move_up.connect(self.move_sort_tier_up)
            sw.move_down.connect(self.move_sort_tier_down)
            
            self.sort_box.content_layout.insertWidget(self.sort_box.content_layout.count() - 1, sw)
            self.sort_tiers.append(sw)
            
        self.loading_settings = False
        self.on_filter_sort_changed()

    def init_ui(self):
        top_layout = QHBoxLayout()
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(30, 30)
        font = QFont()
        font.setPointSize(16)
        self.settings_btn.setFont(font)
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        
        self.fav_view_btn = QPushButton("❤ Favs")
        self.fav_view_btn.setFixedSize(70, 30)
        self.fav_view_btn.clicked.connect(self.show_favorites)
        
        self.back_btn = QPushButton("← Back")
        self.back_btn.setFixedSize(70, 30)
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self.hide_favorites)
        
        self.search_container = QWidget()
        search_layout = QHBoxLayout(self.search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        
        self.loc_input = QLineEdit(self.settings.get("location", ""))
        self.query_input = QLineEdit(self.settings.get("query", ""))
        self.min_price_input = QLineEdit(self.settings.get("min_price", ""))
        self.min_price_input.setPlaceholderText("Min $")
        self.min_price_input.setFixedWidth(60)
        self.max_price_input = QLineEdit(self.settings.get("max_price", ""))
        self.max_price_input.setPlaceholderText("Max $")
        self.max_price_input.setFixedWidth(60)
        self.search_btn = QPushButton("Search")
        
        self.loc_input.textChanged.connect(self.save_current_settings)
        self.query_input.textChanged.connect(self.save_current_settings)
        self.min_price_input.textChanged.connect(self.save_current_settings)
        self.max_price_input.textChanged.connect(self.save_current_settings)
        
        search_layout.addWidget(QLabel(" Location:"))
        search_layout.addWidget(self.loc_input)
        search_layout.addWidget(QLabel("Query:"))
        search_layout.addWidget(self.query_input)
        search_layout.addWidget(QLabel("Price Range:"))
        search_layout.addWidget(self.min_price_input)
        search_layout.addWidget(QLabel("-"))
        search_layout.addWidget(self.max_price_input)
        search_layout.addWidget(self.search_btn)
        
        self.fav_container = QWidget()
        fav_layout = QHBoxLayout(self.fav_container)
        fav_layout.setContentsMargins(0, 0, 0, 0)
        
        self.fav_mode_combo = QComboBox()
        self.fav_mode_combo.addItems(["Wishlist", "Category", "Search Term"])
        self.fav_value_combo = QComboBox()
        
        fav_layout.addWidget(QLabel(" Organize by:"))
        fav_layout.addWidget(self.fav_mode_combo)
        fav_layout.addWidget(QLabel(" Value:"))
        fav_layout.addWidget(self.fav_value_combo)
        fav_layout.addStretch()
        
        self.fav_mode_combo.currentIndexChanged.connect(self.update_fav_values)
        self.fav_value_combo.currentIndexChanged.connect(self.filter_favorites)
        self.fav_container.setVisible(False)
        
        top_layout.addWidget(self.settings_btn)
        top_layout.addWidget(self.fav_view_btn)
        top_layout.addWidget(self.back_btn)
        top_layout.addWidget(self.search_container)
        top_layout.addWidget(self.fav_container)

        self.filter_box = CollapsibleBox("Filters")
        self.add_filter_btn = QPushButton("Add Filter")
        self.add_filter_btn.clicked.connect(self.add_filter_condition)
        self.filter_box.content_layout.addWidget(self.add_filter_btn)

        self.sort_box = CollapsibleBox("Sorting")
        self.add_sort_btn = QPushButton("Add Sort Tier")
        self.add_sort_btn.clicked.connect(self.add_sort_tier)
        self.sort_box.content_layout.addWidget(self.add_sort_btn)
        
        config_layout = QVBoxLayout()
        config_layout.setContentsMargins(0, 5, 0, 5)
        config_layout.addWidget(self.filter_box)
        config_layout.addWidget(self.sort_box)

        self.status_lbl = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.status_lbl)
        status_layout.addWidget(self.progress_bar)
        
        self.splitter = QSplitter(Qt.Horizontal)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(380)
        self.list_widget.setSpacing(5)
        self.list_widget.verticalScrollBar().valueChanged.connect(self.on_scroll)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        top_title_layout = QHBoxLayout()
        self.title_lbl = QLabel("<h2>Item Title</h2>")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        
        self.details_fav_btn = QPushButton("♡")
        self.details_fav_btn.setCheckable(True)
        self.details_fav_btn.setFixedSize(40, 40)
        self.details_fav_btn.setStyleSheet("color: red; font-size: 24px; border: none; background: transparent;")
        self.details_fav_btn.clicked.connect(self.on_details_fav_clicked)
        self.details_fav_btn.setVisible(False)
        
        top_title_layout.addWidget(self.title_lbl)
        top_title_layout.addWidget(self.details_fav_btn)
        
        self.metadata_lbl = QLabel("Select an item to view details.")
        self.metadata_lbl.setWordWrap(True)
        self.metadata_lbl.setOpenExternalLinks(True)
        self.metadata_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        
        self.image_lbl = ImageLabel()
        self.image_lbl.clicked.connect(self.open_fullscreen_viewer)
        
        img_nav_layout = QHBoxLayout()
        self.prev_img_btn = QPushButton("<")
        self.next_img_btn = QPushButton(">")
        self.img_counter_lbl = QLabel("0/0")
        self.img_counter_lbl.setAlignment(Qt.AlignCenter)
        img_nav_layout.addWidget(self.prev_img_btn)
        img_nav_layout.addWidget(self.img_counter_lbl)
        img_nav_layout.addWidget(self.next_img_btn)
        self.prev_img_btn.clicked.connect(self.prev_image)
        self.next_img_btn.clicked.connect(self.next_image)
        
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        right_layout.addLayout(top_title_layout)
        right_layout.addWidget(self.metadata_lbl)
        right_layout.addWidget(self.image_lbl)
        right_layout.addLayout(img_nav_layout)
        right_layout.addWidget(QLabel("<b>Description:</b>"))
        right_layout.addWidget(self.desc_text)
        
        self.splitter.addWidget(self.list_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([450, 850])
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(config_layout)
        main_layout.addWidget(self.splitter, 1)  
        main_layout.addLayout(status_layout)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        
        self.search_btn.clicked.connect(self.perform_search)
        self.list_widget.itemSelectionChanged.connect(self.on_item_selected)

    def keyPressEvent(self, event):
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QComboBox)):
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_Left:
            self.prev_image()
        elif event.key() == Qt.Key_Right:
            self.next_image()
        else:
            super().keyPressEvent(event)
            
    def remove_worker(self, worker, worker_list):
        if worker in worker_list:
            worker_list.remove(worker)
            worker.deleteLater()

    def open_fullscreen_viewer(self):
        if not self.current_item_images:
            return
            
        self.fullscreen_viewer.showFullScreen()
        url = self.current_item_images[self.current_image_index]
        if url in self.image_cache:
            self.fullscreen_viewer.set_image(self.image_cache[url])
        else:
            self.fullscreen_viewer.set_text("Loading...")

    def on_filter_sort_changed(self):
        self.apply_filter_and_sort()
        self.save_current_settings()

    def add_filter_condition(self):
        w = ConditionWidget()
        w.changed.connect(self.on_filter_sort_changed)
        w.removed.connect(self.remove_filter_condition)
        self.filter_box.content_layout.insertWidget(self.filter_box.content_layout.count() - 1, w)
        self.filter_conditions.append(w)
        self.filter_box.expand()
        self.on_filter_sort_changed()

    def remove_filter_condition(self, w):
        self.filter_box.content_layout.removeWidget(w)
        w.deleteLater()
        self.filter_conditions.remove(w)
        self.on_filter_sort_changed()

    def add_sort_tier(self):
        w = SortTierWidget()
        w.changed.connect(self.on_filter_sort_changed)
        w.removed.connect(self.remove_sort_tier)
        w.move_up.connect(self.move_sort_tier_up)
        w.move_down.connect(self.move_sort_tier_down)
        self.sort_box.content_layout.insertWidget(self.sort_box.content_layout.count() - 1, w)
        self.sort_tiers.append(w)
        self.sort_box.expand()
        self.on_filter_sort_changed()

    def remove_sort_tier(self, w):
        self.sort_box.content_layout.removeWidget(w)
        w.deleteLater()
        self.sort_tiers.remove(w)
        self.on_filter_sort_changed()

    def move_sort_tier_up(self, w):
        idx = self.sort_box.content_layout.indexOf(w)
        if idx > 0:
            self.sort_box.content_layout.removeWidget(w)
            self.sort_box.content_layout.insertWidget(idx - 1, w)
            self.sort_tiers.remove(w)
            self.sort_tiers.insert(idx - 1, w)
            self.on_filter_sort_changed()

    def move_sort_tier_down(self, w):
        idx = self.sort_box.content_layout.indexOf(w)
        if idx < self.sort_box.content_layout.count() - 2:
            self.sort_box.content_layout.removeWidget(w)
            self.sort_box.content_layout.insertWidget(idx + 1, w)
            self.sort_tiers.remove(w)
            self.sort_tiers.insert(idx + 1, w)
            self.on_filter_sort_changed()
            
    def show_favorites(self):
        self.in_favorites_view = True
        self.fav_view_btn.setVisible(False)
        self.back_btn.setVisible(True)
        self.search_container.setVisible(False)
        self.fav_container.setVisible(True)
        
        self.update_fav_values()

    def hide_favorites(self):
        self.in_favorites_view = False
        self.fav_view_btn.setVisible(True)
        self.back_btn.setVisible(False)
        self.search_container.setVisible(True)
        self.fav_container.setVisible(False)
        
        self.status_lbl.setText("Returned to search results.")
        self.populate_list(self.listings, append=False)
        
    def update_fav_values(self):
        if not self.in_favorites_view:
            return
            
        mode = self.fav_mode_combo.currentText()
        values = set()
        
        for item in self.favorites.values():
            if mode == "Wishlist":
                values.add(item.get("saved_wishlist", "Default"))
            elif mode == "Category":
                values.add(item.get("saved_category", "Unknown"))
            elif mode == "Search Term":
                values.add(item.get("saved_search_term", "Unknown"))
                
        self.fav_value_combo.blockSignals(True)
        self.fav_value_combo.clear()
        
        sorted_vals = sorted(list(values))
        if mode == "Wishlist" and "Default" in sorted_vals:
            sorted_vals.remove("Default")
            sorted_vals.insert(0, "Default")
            
        self.fav_value_combo.addItems(sorted_vals)
        self.fav_value_combo.blockSignals(False)
        
        self.filter_favorites()
        
    def filter_favorites(self):
        if not self.in_favorites_view:
            return
            
        mode = self.fav_mode_combo.currentText()
        val = self.fav_value_combo.currentText()
        
        filtered_favs = []
        for item in self.favorites.values():
            if mode == "Wishlist" and item.get("saved_wishlist", "Default") == val:
                filtered_favs.append(item)
            elif mode == "Category" and item.get("saved_category", "Unknown") == val:
                filtered_favs.append(item)
            elif mode == "Search Term" and item.get("saved_search_term", "Unknown") == val:
                filtered_favs.append(item)
                
        self.status_lbl.setText(f"Viewing {len(filtered_favs)} favorites in {mode}: '{val}'.")
        self.populate_list(filtered_favs, append=False)

    def on_fav_toggled(self, item_data, checked, button_widget):
        item_id = item_data["id"]
        
        if checked:
            # 1. Immediately save to default (or preserve existing metadata if reapplying)
            fav_item = dict(item_data)
            details = self.listing_details.get(item_id, {})
            cat = details.get("category", "Unknown")
            
            fav_item["saved_search_term"] = self.current_query if self.current_query else "Unknown"
            fav_item["saved_category"] = cat
            fav_item["saved_wishlist"] = "Default"
            
            self.favorites[item_id] = fav_item
            self.save_favorites()
            
            # 2. Show the optional inline Wishlist popup immediately beneath the heart
            existing_wls = set(itm.get("saved_wishlist", "Default") for itm in self.favorites.values())
            self.wishlist_popup = WishlistPopup(existing_wls, "Default", self)
            
            # When the user submits the popup, update the item
            self.wishlist_popup.updated.connect(lambda wl, i_id=item_id: self.update_item_wishlist(i_id, wl))
            
            # Position the popup right below the clicked heart button
            global_pos = button_widget.mapToGlobal(button_widget.rect().bottomLeft())
            self.wishlist_popup.move(global_pos)
            self.wishlist_popup.show()
            
        else:
            if item_id in self.favorites:
                del self.favorites[item_id]
            self.save_favorites()
            
            # Close the popup if it was open while unfavoriting
            if self.wishlist_popup and self.wishlist_popup.isVisible():
                self.wishlist_popup.close()
        
        # Keep the visual state of the heart in sync across both panes
        if self.current_item and self.current_item["id"] == item_id:
            self.details_fav_btn.blockSignals(True)
            self.details_fav_btn.setChecked(checked)
            self.details_fav_btn.setText("❤" if checked else "♡")
            self.details_fav_btn.blockSignals(False)

        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if list_item.data(Qt.UserRole)["id"] == item_id:
                widget = self.list_widget.itemWidget(list_item)
                if hasattr(widget, 'fav_btn'):
                    widget.fav_btn.blockSignals(True)
                    widget.fav_btn.setChecked(checked)
                    widget.fav_btn.setText("❤" if checked else "♡")
                    widget.fav_btn.blockSignals(False)
                break
                
    def update_item_wishlist(self, item_id, new_wishlist):
        if item_id in self.favorites:
            self.favorites[item_id]["saved_wishlist"] = new_wishlist
            self.save_favorites()
            
            # If the user is currently looking at favorites grouped by wishlist, update the view
            if self.in_favorites_view and self.fav_mode_combo.currentText() == "Wishlist":
                self.update_fav_values()

    def on_details_fav_clicked(self, checked):
        if self.current_item:
            self.on_fav_toggled(self.current_item, checked, self.details_fav_btn)

    def perform_search(self):
        self.current_loc = self.loc_input.text().strip()
        self.current_query = self.query_input.text().strip()
        self.current_min_price = self.min_price_input.text().strip()
        self.current_max_price = self.max_price_input.text().strip()
        
        if not self.current_loc or not self.current_query:
            return QMessageBox.warning(self, "Input Error", "Please provide both location and query.")
            
        self.save_current_settings()
        
        self.current_cursor = None
        self.has_next_page = False
        self.current_lat = None
        self.current_lng = None
        
        self.list_widget.clear()
        self.listings.clear()
        self.listing_details.clear()
        self.image_cache.clear()
        
        self.load_listings(is_load_more=False)
            
    def load_listings(self, is_load_more=False):
        if is_load_more and (self.is_loading_more or not self.has_next_page):
            return
            
        self.is_loading_more = True
        pages = int(self.settings.get("pages_per_load", 1))
        
        if not is_load_more:
            self.search_btn.setEnabled(False)
            self.status_lbl.setText("Searching listings...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
        else:
            self.status_lbl.setText(f"Loading more listings... (Loaded: {len(self.listings)})")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            
        self.search_worker = SearchWorker(
            self.current_loc, self.current_query, pages=pages, 
            min_price=self.current_min_price, 
            max_price=self.current_max_price,
            cursor=self.current_cursor,
            lat=self.current_lat,
            lng=self.current_lng
        )
        self.search_worker.finished.connect(
            lambda lst, err, cur, has_next, lat, lng, is_lm=is_load_more:
            self.on_search_finished(lst, err, cur, has_next, lat, lng, is_lm)
        )
        self.search_worker.start()

    def on_search_finished(self, listings, error, cursor, has_next, lat, lng, is_load_more):
        self.is_loading_more = False
        self.search_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if error:
            self.status_lbl.setText("Search failed." if not is_load_more else "Failed to load more.")
            return QMessageBox.critical(self, "Search Error", error)
            
        self.current_cursor = cursor
        self.has_next_page = has_next
        self.current_lat = lat
        self.current_lng = lng
        
        if not is_load_more:
            self.listings = listings
        else:
            self.listings.extend(listings)
            
        self.status_lbl.setText(f"Found {len(self.listings)} listings. Gathering details...")
        self.populate_list(listings, append=is_load_more)
        
    def on_scroll(self, value):
        if self.in_favorites_view:
            return
            
        scrollbar = self.list_widget.verticalScrollBar()
        if value >= scrollbar.maximum() * 0.9: 
            if self.has_next_page and not self.is_loading_more:
                self.load_listings(is_load_more=True)

    def populate_list(self, listings_to_show, append=False):
        if not append:
            self.list_widget.clear()
            self.bg_worker.clear_queue()
        
        for item in listings_to_show:
            list_item = CustomListWidgetItem(self)
            is_fav = item["id"] in self.favorites
            custom_widget = ListingItemWidget(item.get("name", "Unknown"), item.get("currentPrice", "Unknown"), is_fav)
            # Pass the button itself using lambda
            custom_widget.fav_clicked.connect(lambda checked, btn, itm=item: self.on_fav_toggled(itm, checked, btn))
            
            list_item.setSizeHint(custom_widget.sizeHint())
            list_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, custom_widget)
            
            if item["id"] not in self.listing_details:
                self.bg_worker.add_item(item["id"])
        
        self.thumb_worker.add_items(listings_to_show)
        self.apply_filter_and_sort()

    def on_thumbnail_fetched(self, item_id, image_bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(image_bytes):
            for i in range(self.list_widget.count()):
                list_item = self.list_widget.item(i)
                if list_item.data(Qt.UserRole)["id"] == item_id:
                    widget = self.list_widget.itemWidget(list_item)
                    if isinstance(widget, ListingItemWidget):
                        widget.set_thumbnail(pixmap)
                    break
            
    def on_background_fetched(self, item_id, details):
        if item_id not in self.listing_details:
            self.listing_details[item_id] = details
        else:
            self.listing_details[item_id].update(details)
            
        if item_id in self.favorites:
            fav_item = self.favorites[item_id]
            if fav_item.get("saved_category", "Unknown") == "Unknown" and "category" in details:
                fav_item["saved_category"] = details["category"]
                self.save_favorites()
            
        self.apply_filter_and_sort()
        selected = self.list_widget.selectedItems()
        if selected and selected[0].data(Qt.UserRole)["id"] == item_id:
            self.update_right_panel(selected[0].data(Qt.UserRole))
            self.setup_images_for_item(selected[0].data(Qt.UserRole))
            
    def on_demand_fetched(self, item_id, details):
        if item_id not in self.listing_details:
            self.listing_details[item_id] = details
        else:
            self.listing_details[item_id].update(details)
            
        if item_id in self.favorites:
            fav_item = self.favorites[item_id]
            if fav_item.get("saved_category", "Unknown") == "Unknown" and "category" in details:
                fav_item["saved_category"] = details["category"]
                self.save_favorites()
            
        self.apply_filter_and_sort()
        selected = self.list_widget.selectedItems()
        if selected and selected[0].data(Qt.UserRole)["id"] == item_id:
            self.update_right_panel(selected[0].data(Qt.UserRole))
            self.setup_images_for_item(selected[0].data(Qt.UserRole))

    def apply_filter_and_sort(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            data = item.data(Qt.UserRole)
            details = self.listing_details.get(data["id"], {})
            
            title = str(data.get("name", "")).lower()
            desc = str(details.get("description", "")).lower()
            attrs = " ".join([f"{k} {v}" for k, v in details.get("attributes", {}).items()]).lower()
            
            visible = True
            for cw in self.filter_conditions:
                if not cw.evaluate(title, desc, attrs):
                    visible = False
                    break
            item.setHidden(not visible)

        if self.sort_tiers:
            self.list_widget.sortItems(Qt.AscendingOrder)
            
    def get_tier_value(self, tier, data, details):
        sort_type = tier.type_combo.currentText()
        if sort_type == "Price":
            return parse_price(data.get("currentPrice"))
        elif sort_type == "Time Listed":
            return details.get("creation_time", 0)
        elif sort_type == "Distance":
            return 0 
        elif sort_type == "Item Condition":
            return get_condition_score(details.get("attributes", {}).get("Condition", ""))
        elif sort_type == "Conditions Matched":
            score = 0
            title = str(data.get("name", "")).lower()
            desc = str(details.get("description", "")).lower()
            attrs = " ".join([f"{k} {v}" for k, v in details.get("attributes", {}).items()]).lower()
            for cw in tier.conditions:
                if cw.evaluate(title, desc, attrs):
                    score += 1
            return score
        return 0

    def compare_items(self, item1, item2):
        d1 = item1.data(Qt.UserRole)
        d2 = item2.data(Qt.UserRole)
        det1 = self.listing_details.get(d1['id'], {})
        det2 = self.listing_details.get(d2['id'], {})
        
        for tier in self.sort_tiers:
            v1 = self.get_tier_value(tier, d1, det1)
            v2 = self.get_tier_value(tier, d2, det2)
            
            if v1 != v2:
                if tier.dir_combo.currentText() == "Ascending":
                    return v1 < v2
                else:
                    return v1 > v2
        return False

    def on_item_selected(self):
        selected = self.list_widget.selectedItems()
        if not selected: return
        
        item_data = selected[0].data(Qt.UserRole)
        item_id = item_data["id"]
        
        details = self.listing_details.get(item_id, {})
        needs_desc = not details.get("description") and "description" not in details
        needs_imgs = details.get("image_urls") is None
        
        self.update_right_panel(item_data)
        
        if needs_desc or needs_imgs:
            self.metadata_lbl.setText(self.metadata_lbl.text() + "<br><i>Loading additional details...</i>")
            if needs_desc:
                self.desc_text.setPlainText("Loading details on demand...")
                
            worker = OnDemandWorker(item_id, fetch_desc=needs_desc, fetch_images=needs_imgs)
            worker.details_fetched.connect(self.on_demand_fetched)
            worker.finished.connect(lambda w=worker: self.remove_worker(w, self.ondemand_workers))
            self.ondemand_workers.append(worker)
            worker.start()
        else:
            self.setup_images_for_item(item_data)

    def setup_images_for_item(self, item_data):
        item_id = item_data["id"]
        details = self.listing_details.get(item_id, {})
        urls = details.get("image_urls", [])
        if not urls:
            urls = [item_data.get("primaryPhotoURL")] if item_data.get("primaryPhotoURL") else []
            
        self.current_item_images = urls
        self.current_image_index = 0
        self.load_current_image()

    def load_current_image(self):
        if not self.current_item_images:
            self.image_lbl.setText("No image available.")
            self.img_counter_lbl.setText("0/0")
            self.prev_img_btn.setEnabled(False)
            self.next_img_btn.setEnabled(False)
            if self.fullscreen_viewer.isVisible():
                self.fullscreen_viewer.set_text("No image available.")
            return

        total = len(self.current_item_images)
        self.img_counter_lbl.setText(f"{self.current_image_index + 1}/{total}")
        self.prev_img_btn.setEnabled(self.current_image_index > 0)
        self.next_img_btn.setEnabled(self.current_image_index < total - 1)

        url = self.current_item_images[self.current_image_index]
        if not url: 
            self.image_lbl.setText("No image available.")
            if self.fullscreen_viewer.isVisible():
                self.fullscreen_viewer.set_text("No image available.")
            return

        if url in self.image_cache:
            self.update_image_label(self.image_cache[url])
        else:
            self.image_lbl.setText("Loading image...")
            if self.fullscreen_viewer.isVisible():
                self.fullscreen_viewer.set_text("Loading...")
            worker = ImageWorker(url)
            worker.image_fetched.connect(self.on_image_fetched)
            self.image_workers.append(worker)
            worker.start()

    def prev_image(self):
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.load_current_image()

    def next_image(self):
        if self.current_image_index < len(self.current_item_images) - 1:
            self.current_image_index += 1
            self.load_current_image()

    def update_right_panel(self, item_data):
        self.current_item = item_data
        
        self.title_lbl.setText(f"<h2>{item_data.get('name', 'N/A')}</h2>")
        
        self.details_fav_btn.setVisible(True)
        is_fav = item_data["id"] in self.favorites
        self.details_fav_btn.blockSignals(True)
        self.details_fav_btn.setChecked(is_fav)
        self.details_fav_btn.setText("❤" if is_fav else "♡")
        self.details_fav_btn.blockSignals(False)
        
        price = item_data.get('currentPrice', 'N/A')
        seller = f"{item_data.get('sellerName', 'N/A')} ({item_data.get('sellerType', 'N/A')})"
        loc = item_data.get('sellerLocation', 'N/A')
        meta_html = f"<b>Price:</b> {price}<br><b>Seller:</b> {seller}<br><b>Location:</b> {loc}<br>"
        
        details = self.listing_details.get(item_data["id"])
        
        if details and ("description" in details):
            status_list = []
            if details.get("is_live"): status_list.append("Live")
            if details.get("is_pending"): status_list.append("Pending")
            if details.get("is_sold"): status_list.append("Sold")
            status_str = ", ".join(status_list) if status_list else "Unknown"
            category = details.get("category", "N/A")
            delivery = details.get("delivery_types", [])
            del_str = ", ".join(delivery) if delivery else "N/A"
            created = details.get("creation_time")
            created_str = datetime.datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S') if isinstance(created, (int, float)) else "N/A"
            link = details.get("share_uri", "")
            link_str = f"<a href='{link}'>View on Facebook</a>" if link else "N/A"
            
            meta_html += f"<b>Status:</b> {status_str}<br><b>Category:</b> {category}<br>"
            attrs = details.get("attributes", {})
            if attrs:
                meta_html += "<b>Attributes:</b><br>"
                for k, v in attrs.items(): meta_html += f"&nbsp;&nbsp;&nbsp;&nbsp;• {k}: {v}<br>"
            meta_html += f"<b>Delivery:</b> {del_str}<br><b>Listed:</b> {created_str}<br><b>Link:</b> {link_str}"
            self.desc_text.setPlainText(details.get("description", "No description provided."))
        else:
            self.desc_text.setPlainText("")
            
        self.metadata_lbl.setText(meta_html)

    def on_image_fetched(self, url, image_bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        self.image_cache[url] = pixmap
        self.image_workers = [w for w in self.image_workers if w.isRunning()]
        
        if self.current_item_images and self.current_image_index < len(self.current_item_images):
            if self.current_item_images[self.current_image_index] == url:
                self.update_image_label(pixmap)

    def update_image_label(self, pixmap):
        self.image_lbl.setPixmap(pixmap)
        if self.fullscreen_viewer.isVisible():
            self.fullscreen_viewer.set_image(pixmap)

    def closeEvent(self, event):
        self.save_current_settings()
        self.bg_worker.stop()
        self.bg_worker.quit()
        self.thumb_worker.stop()
        self.thumb_worker.quit()
        for w in self.ondemand_workers:
            w.quit()
        if self.wishlist_popup:
            self.wishlist_popup.close()
        self.fullscreen_viewer.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MarketplaceApp()
    window.show()
    sys.exit(app.exec_())