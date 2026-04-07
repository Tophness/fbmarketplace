# Facebook Marketplace API & Desktop Browser

A powerful, dual-purpose project featuring an easy-to-use Facebook Marketplace API and a feature-rich standalone Desktop Application. Both function by wrapping the internal Facebook GraphQL API, allowing for quick retrieval of Marketplace listings, detailed item data, and images **without requiring a Facebook account**.

## Features

* **Standalone Desktop App (`app.py`)**: A PyQt5-based browser with advanced multi-tier sorting, keyword filtering, background image/description caching, proxy support, and a built-in wishlist/favorites system.
* **Scraper Core (`MarketplaceScraper.py`)**: Directly queries Facebook's GraphQL endpoints. Supports pagination (cursors), rate-limit handling, local JSON caching, and fetches deep metadata (delivery types, categories, extra photos).
* **Flask API (`MarketplaceAPI.py`)**: A lightweight local web server that exposes the scraper functionality via simple REST endpoints.

---

## Screenshots
<img width="1302" height="1748" alt="image" src="https://github.com/user-attachments/assets/ecd1d414-ab46-415a-8e28-9da4a77e6421" />
<img width="402" height="419" alt="image" src="https://github.com/user-attachments/assets/8d4e1825-aa46-4232-89c9-3b664ba3d0d8" />
<img width="1302" height="1748" alt="image" src="https://github.com/user-attachments/assets/6eceebcc-e686-4d48-89e7-e79835fd3261" />
<img width="3840" height="2110" alt="image" src="https://github.com/user-attachments/assets/6c76149e-d33b-4701-bc9d-dacce1fe0845" />



## Installation

1. Clone or download the repository.
2. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## The Desktop Application

The desktop app provides a seamless browsing experience outside of the browser. 

**To run the app:**
```bash
python app.py
```

**Key Features:**
* **Background Fetching**: Automatically fetches item descriptions, attributes, and high-res images in the background as you scroll.
* **Favorites & Wishlists**: Save items, group them by category, or assign them to custom Wishlists.
* **Advanced Filters**: Filter results by exact matches, exclusions, or partial matches across titles, descriptions, and item attributes.
* **Multi-Tier Sorting**: Sort by Price, Time Listed, Condition, or by how many custom conditions an item matches.
* **Proxy Support**: Configure proxies right from the settings menu to prevent rate-limiting.

---

## The Flask API

If you prefer to integrate this into your own project, you can run the local Flask server.

**To run the API:**
```bash
python MarketplaceAPI.py
```

### API Responses

**All** endpoints will return a JSON response in the following format:
```json
{
    "status": "Success",
    "error": {
        "source": "Facebook",
        "message": "Rate limited"
    },
    "data": {}
}
```
* `status`: "Success" or "Failure".
* `error`: Will be empty if no error exists. Contains `source` ("Facebook", "User", or "Parsing") and `message`.
* `data`: Contains the requested information.

---

### Endpoints

#### 1. `/locations`
Retrieves locations which are exact or close matches to the query. Latitude and longitude are required for the `/search` endpoint.

**Method:** `GET`

**Parameters:**
* `locationQuery` (String, Required) - A location name to search for.

**Example Request:** `/locations?locationQuery=Houston`

**Example Response:**
```json
{
    "status": "Success",
    "error": {},
    "data": {
        "locations": [
            {
                "name": "Houston, Texas",
                "latitude": "29.7602",
                "longitude": "-95.3694"
            }
        ]
    }
}
```

#### 2. `/search`
Retrieves listings matching the provided query, coordinates, and filters.

**Method:** `GET`

**Parameters:**
* `locationLatitude` (String, Required) - Latitude coordinate.
* `locationLongitude` (String, Required) - Longitude coordinate.
* `listingQuery` (String, Required) - Keywords to search for.
* `numPageResults` (Integer, Optional) - Number of pages to load in a single request (Default: 1).
* `minPrice` (Integer, Optional) - Minimum price bound.
* `maxPrice` (Integer, Optional) - Maximum price bound.
* `cursor` (String, Optional) - Pagination cursor to get the next page of results.

**Example Request:** `/search?locationLatitude=29.7602&locationLongitude=-95.3694&listingQuery=couch&minPrice=100&maxPrice=500`

**Example Response:**
```json
{
    "status": "Success",
    "error": {}, 
    "data": {
        "listingPages": [
            {
                "listings": [
                    {
                        "id": "4720490308074106",
                        "name": "Small sectional couch", 
                        "currentPrice": "$150",
                        "previousPrice": "",
                        "saleIsPending": "false",
                        "primaryPhotoURL": "https://...",
                        "sellerName": "John Doe",
                        "sellerLocation": "Houston, Texas",
                        "sellerType": "User"
                    }
                ]
            }
        ],
        "page_info": {
            "end_cursor": "AQAxYz...==",
            "has_next_page": true
        }
    }
}
```
*(Note: To fetch the next page, pass the `end_cursor` value into the `cursor` parameter on your next request).*
