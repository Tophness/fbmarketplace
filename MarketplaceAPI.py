from flask import Flask, request
import MarketplaceScraper

API = Flask(__name__)


@API.route("/locations", methods=["GET"])
def locations():
    response = {}

    locationQuery = request.args.get("locationQuery")

    if (locationQuery):
        status, error, data = MarketplaceScraper.getLocations(
            locationQuery=locationQuery)
    else:
        status = "Failure"
        error = {}
        error["source"] = "User"
        error["message"] = "Missing required parameter"
        data = {}

    response["status"] = status
    response["error"] = error
    response["data"] = data

    return response


@API.route("/search", methods=["GET"])
def search():
    response = {}

    locationLatitude = request.args.get("locationLatitude")
    locationLongitude = request.args.get("locationLongitude")
    listingQuery = request.args.get("listingQuery")
    minPrice = request.args.get("minPrice")
    maxPrice = request.args.get("maxPrice")
    cursor = request.args.get("cursor")
    
    try:
        numPageResults = int(request.args.get("numPageResults", 1))
    except ValueError:
        numPageResults = 1

    if (locationLatitude and locationLongitude and listingQuery):
        status, error, data = MarketplaceScraper.getListings(
            locationLatitude=locationLatitude, 
            locationLongitude=locationLongitude, 
            listingQuery=listingQuery,
            numPageResults=numPageResults,
            minPrice=minPrice,
            maxPrice=maxPrice,
            cursor=cursor
        )
    else:
        status = "Failure"
        error = {}
        error["source"] = "User"
        error["message"] = "Missing required parameter(s)"
        data = {}

    response["status"] = status
    response["error"] = error
    response["data"] = data

    return response

if __name__ == "__main__":
    API.run(debug=True)