from starlette.responses import RedirectResponse
from pymongo import MongoClient, errors, collection as pymongocollection
from fastapi import FastAPI, Header, Response, status
from typing import Optional
from hashlib import blake2b
from pydantic import BaseModel
import csv
import os


app = FastAPI()
# CHANGE TO ENV
client = MongoClient(os.environ['DATABASE_URL'], int(os.environ['DATABASE_PORT'])) # https://stargods.net:43751/
database_name = os.environ['DATABASE_NAME'] # codesdb
db = client[database_name]
collection_post_schema = "-assets"

class EditableAsset(BaseModel):
    contents: list
    notes: str
    inuse: bool


def get_apikey(username, password):
    h = blake2b(key=bytes(password.encode("UTF-8")), digest_size=8)
    h.update(username.encode("UTF-8"))
    d = h.hexdigest()
    return d


def parse_headers(header):
    # Parse Header String
    try:
        headers = iter(header.split())
        headerdict = dict()
        for thing in headers:
            if thing.find(":"):
                headerdict[thing.strip(":")] = headers.__next__()
        return headerdict
    except:
        raise


def parse_headers_userdata(header):
    return parse_headers(header)['USERNAME'], parse_headers(header)['PASSWORD']

def parse_headers_apikey(header):
    return parse_headers(header)['X-API-KEY']


# ----------GENERAL------------------
@app.get("/")
def root() -> RedirectResponse:
    """Redirects the root ("/") to the /docs url."""
    return RedirectResponse(url='/docs')


# GET /api/code {json} # "Get Existing Box"
@app.get("/api/{item_code}")
def get_item(item_code: str, header: Optional[str] = Header(None)):
    """
    Returns a JSON representing the given user via the provided ID.
    Does not return the _id ObjectID, as this is for internal mongo purposes.
    - param item_code: item code
    - return: JSON string
    """
    collection = db[parse_headers_apikey(header)]
    ret = collection.find_one({"code": item_code})
    ret.pop("_id")
    return ret

# GET /api/?query&query {json} # "Get Query"
@app.get("/api/")
def get_item(limit: int = 10,
             inuse: Optional[bool] = None,
             serial: Optional[int] = None,
             notes: Optional[str] = None,
             name: Optional[str] = None,
             header: Optional[str] = Header(None)):
    collection = db[parse_headers_apikey(header)]
    query = {}
    if inuse is not None:
        query.update({f"inuse": inuse})
    if serial is not None:
        query.update({f"serial": serial})
    if notes is not None:
        query.update({f"notes": notes})
    if name is not None:
        query.update({f"name": name})
    ret = [elem for elem in collection.find(query, limit=limit)]
    [elem.pop("_id") for elem in ret]
    return ret

# PUT /api/code {json} # "Enable New Box, Set Notes"
@app.put("/api/{item_code}")
def put_item(item_code: str, asset: EditableAsset, header: Optional[str] = Header(None)):
    collection = db[parse_headers_apikey(header)]
    collection.update_one({"code": item_code},
                          {"$set": {"notes": asset.notes, "contents": asset.contents, "inuse": asset.inuse}})
    ret = collection.find_one({"code": item_code})
    ret.pop("_id")
    return ret


# DELETE /api/code # "De-activate Existing Box"
@app.delete("/api/{item_code}")
def delete_item(item_code: str, header: Optional[str] = Header(None)):
    collection = db[parse_headers_apikey(header)]
    collection.update_one({"code": item_code}, {"$set": {"inuse": False}})
    return collection.find_one({"code": item_code})


# ----------USERS------------------
# GET /api/users  {json, no api key} # "Get api key for username/password. Essentially is a login"
@app.get("/api/users/")
def get_user(response: Response, header: Optional[str] = Header(None)):
    try:
        # Parse Headers
        username, password = parse_headers_userdata(header)
        # Check if user exists
        assert db.command({"usersInfo": username})["users"]
        # Hash username using password, check if collection exists
        key = get_apikey(username=username, password=password)
        assert key in db.collection_names()
        return {"X-API-KEY": key}
    except AssertionError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return response


# # POST /api/users  {json, no api key} # "Create new user,collection, role, return api key"
@app.post("/api/users/")
def post_user(response: Response, header: Optional[str] = Header(None)):
    ret_dict = dict()
    # Parse Headers
    username, password = parse_headers_userdata(header)
    # Create Collection and Mongo User
    print(db.create_collection(get_apikey(username=username, password=password)))
    print(db.command("createRole",
               f'{get_apikey(username=username, password=password)}_CollectionRole',
               privileges=[{"resource": {'db': f'{database_name}', 'collection': f"{username}"},
                            "actions": ['find', 'update', 'insert']}],
               roles=[]))

    print(db.command("createUser", username, pwd=password,
                     roles=[f'{get_apikey(username=username, password=password)}_CollectionRole']))
    # Hash username using password for API key
    key = get_apikey(username=username, password=password)
    # Return api key
    # ret_dict = db.command({"usersInfo": username})["users"][0]
    ret_dict["X-API-KEY"] = key

    # POPULATE THE INIT COLLECTION FROM CODES.CSV
    collection = db[key]
    insert = list()
    with open('codes.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            dicte = {"serial": int(row["serial"]),
                                   "code": row["code"],
                                   "name": row["name"],
                                   "namecode": row["namecode"],
                                   "contents": [],
                                   "notes": row["notes"],
                                   "inuse": False}
            insert.append(dicte)
            # serial,code,name,namecode,URL,notes,inuse
    print(collection.insert(insert))
    return ret_dict

# # DELETE /api/users  {admin api key} # "Create new user,collection, role, return api key"
@app.delete("/api/users/")
def delete_user(response: Response, header: Optional[str] = Header(None)):
    # !FUTURE check for admin api key
    # Parse Headers
    try:
        username, password = parse_headers_userdata(header)
        db.drop_collection(get_apikey(username=username, password=password))
        print(db.command({"dropRole": f'{get_apikey(username=username, password=password)}_CollectionRole'}))
        print(db.command({"dropUser": username}))
        response.status_code = status.HTTP_200_OK
        return response
    except errors.OperationFailure:
        response.status_code = status.HTTP_400_BAD_REQUEST
    print(db.command({"dropRole": f'{get_apikey(username=username, password=password)}_CollectionRole'}))
    print(db.command({"dropUser": username}))
    return response


