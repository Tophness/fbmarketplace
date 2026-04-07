import requests
import json
import copy
import os
import time

GRAPHQL_URL = "https://www.facebook.com/api/graphql/"
GRAPHQL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
PROXY_CONFIG = {}

SCRAPER_SESSION = requests.Session()

def update_session_proxy(proxies):
    SCRAPER_SESSION.proxies = proxies
    SCRAPER_SESSION.cookies.clear()

def safe_get(obj, *keys, default=None):
    try:
        for key in keys:
            if obj is None:
                return default
            obj = obj.get(key)
        return obj if obj is not None else default
    except AttributeError:
        return default

def getLocations(locationQuery):
    data = {}

    requestPayload = {
        "variables": """{"params": {"caller": "MARKETPLACE", "page_category": ["CITY", "SUBCITY", "NEIGHBORHOOD","POSTAL_CODE"], "query": "%s"}}""" % (locationQuery),
        "doc_id": "5585904654783609"
    }

    status, error, facebookResponse = getFacebookResponse(requestPayload)

    if status == "Success":
        data["locations"] = []
        facebookResponseJSON = json.loads(facebookResponse.text)

        edges = safe_get(facebookResponseJSON, "data", "city_street_search", "street_results", "edges", default=[])

        for location in edges:
            node = location.get("node", {})

            locationName = safe_get(node, "subtitle", default="")
            if locationName:
                locationName = locationName.split(" \u00b7")[0]

            if locationName == "City" or not locationName:
                locationName = safe_get(node, "single_line_address", default="")
                
            if not locationName:
                locationName = safe_get(node, "name", default="Unknown Location")

            lat = safe_get(node, "location", "latitude")
            lng = safe_get(node, "location", "longitude")

            if lat and lng:
                data["locations"].append({
                    "name": locationName,
                    "latitude": str(lat),
                    "longitude": str(lng)
                })

    return (status, error, data)

def getListings(locationLatitude, locationLongitude, listingQuery, numPageResults=1, minPrice=None, maxPrice=None, cursor=None, delay=0.0):
    data = {}
    rawPageResults = []
    
    try: lower_bound = int(minPrice) * 100
    except: lower_bound = 0
    
    try: upper_bound = int(maxPrice) * 100
    except: upper_bound = 214748364700

    variables_dict = {
        "count": 24,
        "params": {
            "bqf": {
                "callsite": "COMMERCE_MKTPLACE_WWW", 
                "query": listingQuery
            },
            "browse_request_params": {
                "commerce_enable_local_pickup": True,
                "commerce_enable_shipping": True,
                "commerce_search_and_rp_available": True,
                "filter_location_latitude": float(locationLatitude),
                "filter_location_longitude": float(locationLongitude),
                "filter_price_lower_bound": lower_bound,
                "filter_price_upper_bound": upper_bound,
                "filter_radius_km": 20
            },
            "custom_request_params": {"surface": "SEARCH"}
        }
    }

    if cursor:
        variables_dict["cursor"] = cursor

    requestPayload = {
        "variables": json.dumps(variables_dict),
        "doc_id": "7111939778879383"
    }

    status, error, facebookResponse = getFacebookResponse(requestPayload)

    if status != "Success":
        return (status, error, data)

    facebookResponseJSON = json.loads(facebookResponse.text)
    rawPageResults.append(facebookResponseJSON)

    for _ in range(1, numPageResults):
        pageInfo = safe_get(facebookResponseJSON, "data", "marketplace_search", "feed_units", "page_info")

        if not pageInfo or not pageInfo.get("has_next_page"):
            break

        next_cursor = pageInfo.get("end_cursor")
        if not next_cursor:
            break

        if delay > 0:
            time.sleep(delay)

        requestPayloadCopy = copy.copy(requestPayload)
        
        try:
            vars_dict = json.loads(requestPayloadCopy["variables"])
            vars_dict["cursor"] = next_cursor
            requestPayloadCopy["variables"] = json.dumps(vars_dict)
        except Exception:
            break

        next_status, next_error, facebookResponse = getFacebookResponse(requestPayloadCopy)

        if next_status != "Success":
            break

        facebookResponseJSON = json.loads(facebookResponse.text)
        rawPageResults.append(facebookResponseJSON)

    finalPageInfo = safe_get(facebookResponseJSON, "data", "marketplace_search", "feed_units", "page_info") or {}

    data["listingPages"] = parsePageResults(rawPageResults)
    data["page_info"] = {
        "end_cursor": finalPageInfo.get("end_cursor"),
        "has_next_page": finalPageInfo.get("has_next_page", False)
    }

    return ("Success", {}, data)

def getListingDetails(listingID):
    data = {}
    cache_dir = "cache"
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"listing_{listingID}.json")

    res_json = None

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                res_json = json.load(f)
                if res_json.get("errors") or not safe_get(res_json, "data", "viewer", "marketplace_product_details_page", "target"):
                    res_json = None
                    try: os.remove(cache_path)
                    except: pass
        except Exception:
            res_json = None

    if not res_json:
        base_variables = {
            "enableJobEmployerActionBar": False,
            "enableJobSeekerActionBar": False,
            "feedbackSource": 56,
            "feedLocation": "MARKETPLACE_MEGAMALL",
            "referralCode": "null",
            "referralSurfaceString": "search",
            "scale": 1,
            "targetId": str(listingID),
            "useDefaultActor": False,
            "__relay_internal__pv__ShouldUpdateMarketplaceBoostListingBoostedStatusrelayprovider": False,
            "__relay_internal__pv__CometUFISingleLineUFIrelayprovider": False,
            "__relay_internal__pv__CometUFIShareActionMigrationrelayprovider": True,
            "__relay_internal__pv__CometUFIReactionsEnableShortNamerelayprovider": False,
            "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "ORIGINAL",
            "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
            "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
            "__relay_internal__pv__IsWorkUserrelayprovider": False,
            "__relay_internal__pv__GHLShouldChangeSponsoredDataFieldNamerelayprovider": False,
            "__relay_internal__pv__GHLShouldChangeAdIdFieldNamerelayprovider": False,
            "__relay_internal__pv__CometUFI_dedicated_comment_routable_dialog_gkrelayprovider": True
        }

        payload = {
            "doc_id": "26924013917190310",
            "variables": json.dumps(base_variables)
        }

        status, error, facebookResponse = getFacebookResponse(payload)
        
        if status != "Success":
            return ("Failure", {"source": "Facebook", "message": error.get('message', 'Unknown Error')}, {})

        try:
            res_json = json.loads(facebookResponse.text)
            
            target = safe_get(res_json, "data", "viewer", "marketplace_product_details_page", "target")
            if target is not None:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(res_json, f, indent=2, ensure_ascii=False)
            else:
                return ("Failure", {"source": "Facebook", "message": "Rate limited or item unavailable."}, {})
        except Exception as e:
            return ("Failure", {"source": "Parsing", "message": f"Parsing error: {str(e)}"}, {})

    try:
        if not res_json.get("data"):
            return ("Failure", {"source": "Facebook", "message": "Returned null data."}, {})

        target = safe_get(res_json, "data", "viewer", "marketplace_product_details_page", "target")
        
        if not target:
            return ("Failure", {"source": "Parsing", "message": "Could not locate 'target' node in JSON."}, {})

        desc_text = safe_get(target, "redacted_description", "text")
        data["description"] = desc_text.replace('\\n', '\n').strip() if desc_text else "No description provided."
        data["title"] = target.get("marketplace_listing_title")
        data["creation_time"] = target.get("creation_time")
        data["location_text"] = safe_get(target, "location_text", "text")
        data["is_live"] = target.get("is_live")
        data["is_pending"] = target.get("is_pending")
        data["is_sold"] = target.get("is_sold")
        data["delivery_types"] = target.get("delivery_types", [])
        data["share_uri"] = target.get("share_uri")
        data["category"] = safe_get(target, "marketplaceListingRenderableIfLoggedOut", "marketplace_listing_category_name")
        raw_attributes = target.get("attribute_data", [])
        data["attributes"] = {
            attr.get("attribute_name", "Unknown"): attr.get("label", attr.get("value"))
            for attr in raw_attributes
        }

        return ("Success", {}, data)
            
    except Exception as e:
        return ("Failure", {"source": "Parsing", "message": f"Parsing error: {str(e)}"}, {})

def getListingImages(listingID):
    cache_dir = "cache"
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"images_{listingID}.json")

    res_json = None

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                res_json = json.load(f)
                if res_json.get("errors") or safe_get(res_json, "data", "viewer", "marketplace_product_details_page", "target", "listing_photos") is None:
                    res_json = None
                    try: os.remove(cache_path)
                    except: pass
        except Exception:
            res_json = None

    if not res_json:
        payload = {
            "doc_id": "10059604367394414",
            "variables": json.dumps({"targetId": str(listingID)})
        }
        
        status, error, facebookResponse = getFacebookResponse(payload)
        
        if status != "Success":
            return ("Failure", error, [])
        
        try:
            res_json = json.loads(facebookResponse.text)
            
            photos = safe_get(res_json, "data", "viewer", "marketplace_product_details_page", "target", "listing_photos")
            if photos is not None:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(res_json, f, indent=2, ensure_ascii=False)
            else:
                return ("Failure", {"source": "Facebook", "message": "Rate limited or item unavailable."}, [])
        except Exception as e:
            return ("Failure", {"source": "Parsing", "message": str(e)}, [])
            
    try:
        photos = safe_get(res_json, "data", "viewer", "marketplace_product_details_page", "target", "listing_photos", default=[])
        image_urls = [safe_get(photo, "image", "uri") for photo in photos if safe_get(photo, "image", "uri")]
        return ("Success", {}, image_urls)
    except Exception as e:
        return ("Failure", {"source": "Parsing", "message": str(e)}, [])

def getFacebookResponse(requestPayload):
    try:
        facebookResponse = SCRAPER_SESSION.post(
            GRAPHQL_URL, 
            headers=GRAPHQL_HEADERS, 
            data=requestPayload, 
            timeout=20
        )

        try:
            res_json = facebookResponse.json()
            if res_json.get("errors"):
                error_msg = res_json["errors"][0].get("message", "Unknown API Error")
                return ("Failure", {"source": "Facebook", "message": error_msg}, facebookResponse)
        except:
            pass

        return ("Success", {}, facebookResponse)
    except Exception as e:
        return ("Failure", {"source": "Request", "message": str(e)}, None)

def parsePageResults(rawPageResults):
    listingPages = []

    for rawPageResult in rawPageResults:
        pageListings = []
        edges = safe_get(rawPageResult, "data", "marketplace_search", "feed_units", "edges", default=[])

        for listing in edges:
            node = listing.get("node", {})

            if node.get("__typename") != "MarketplaceFeedListingStoryObject":
                continue

            listing_data = node.get("listing")
            if not listing_data:
                continue

            try:
                pageListings.append({
                    "id": listing_data.get("id"),
                    "name": listing_data.get("marketplace_listing_title"),
                    "currentPrice": safe_get(listing_data, "listing_price", "formatted_amount"),
                    "previousPrice": safe_get(listing_data, "strikethrough_price", "formatted_amount", default=""),
                    "saleIsPending": str(listing_data.get("is_pending", False)).lower(),
                    "primaryPhotoURL": safe_get(listing_data, "primary_listing_photo", "image", "uri"),
                    "sellerName": safe_get(listing_data, "marketplace_listing_seller", "name", default="Unknown"),
                    "sellerLocation": safe_get(listing_data, "location", "reverse_geocode", "city_page", "display_name", default=""),
                    "sellerType": safe_get(listing_data, "marketplace_listing_seller", "__typename", default="")
                })

            except Exception:
                continue

        listingPages.append({"listings": pageListings})

    return listingPages