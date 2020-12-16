from starlette.responses import RedirectResponse
from pymongo import MongoClient, errors, collection as pymongocollection
from fastapi import FastAPI, Header, Response, status, Security
from fastapi.security.api_key import APIKeyHeader
import secrets
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from hashlib import blake2b
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import treepoem
from PIL import Image, ImageDraw, ImageFont, ImageOps
import csv
import os
import uvicorn
import aiofiles  # required for certain FASTAPI File Responses
from reportlab.lib.pagesizes import LETTER, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, Spacer
from reportlab.platypus import Image as platyImage
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from zipfile import ZipFile

app = FastAPI()
security = HTTPBasic()
api_admin_username = os.environ['API_USERNAME']
api_admin_password = os.environ['API_PASSWORD']
client = MongoClient(os.environ['DATABASE_URL'], int(os.environ['DATABASE_PORT'])) # https://stargods.net:43751/
database_name = os.environ['DATABASE_NAME'] # codesdb
db = client[database_name]
collection_post_schema = "-assets"
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)
# ---------------------------------------------------------------------
HALF_SIZE = False
if HALF_SIZE:
    LABEL_SIZE = (160, 200)  # 450, 200
else:
    LABEL_SIZE = (600, 200)

class EditableAsset(BaseModel):
    contents: list = Field(default=[], example=[])
    notes: str = Field(default="", example="")
    inuse = False

origins = [
    "http://localhost",
    "http://localhost:4200/",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def gen_label(entry_dict: dict, api_key):
    """
    Generates a label from an entry.
    :param entry_dict: Must contain all standard keys such as name, namecode, notes, contents, etc
    :param api_key: your api key, only used to write to unique filename
    :return: (filename, image), does not write to file
    """
    im = Image.new('RGB', LABEL_SIZE, (0, 0, 0))
    draw = ImageDraw.Draw(im)
    result_img = treepoem.generate_barcode("datamatrix", entry_dict["code"], options={"version": "12x12"})
    result_img = ImageOps.invert(result_img).convert('1')  # invert
    result_img = ImageOps.crop(result_img, 1)
    result_img = result_img.resize((100, 100))
    Image.Image.paste(im, result_img, (30, 25))
    font = ImageFont.truetype(r'fonts/Futura.ttc', 40)
    font2 = ImageFont.truetype(r'fonts/Futura.ttc', 35)
    efon_font = ImageFont.truetype(r'fonts/Efon.ttf', 120)
    draw.text((31, 130), entry_dict["code"], font=font)
    draw.text((160, 15), entry_dict["name"], font=font2)
    draw.text((180, 75), entry_dict["namecode"], font=efon_font)
    filename = f'generated-labels/{api_key}-{entry_dict["code"]}.png'
    return filename, im


def get_apikey(username, password):
    h = blake2b(key=bytes(password.encode("UTF-8")), digest_size=8)
    h.update(username.encode("UTF-8"))
    d = h.hexdigest()
    return d


# DEPRECATED
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


# DEPRECATED
def parse_headers_userdata(header):
    return parse_headers(header)['USERNAME'], parse_headers(header)['PASSWORD']


# DEPRECATED
def parse_headers_apikey(header):
    return parse_headers(header)['X-API-KEY']


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, api_admin_username)
    correct_password = secrets.compare_digest(credentials.password, api_admin_password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ----------GENERAL------------------
@app.get("/", include_in_schema=False)
def root(username: str = Depends(get_current_username)) -> RedirectResponse:
    """Redirects the root ("/") to the /docs url."""
    return RedirectResponse(url='/docs')


# GET /api/code {json} # "Get Existing Box"
@app.get("/api/{item_code}")
def get_item(item_code: str, api_key: Optional[str] = Security(api_key_header)):
    """
    Returns a JSON representing the given user via the provided ID.
    Does not return the _id ObjectID, as this is for internal mongo purposes.
    - param item_code: item code
    - return: JSON string
    """
    if item_code is None or not item_code:
        raise HTTPException(status_code=404, detail="Invalid/Empty query")
    collection = db[api_key]
    ret = collection.find_one({"code": item_code})
    ret.pop("_id")
    return ret


# GET /api/next # "Get Next Available Box"
@app.get("/api/next/")
def get_next_free_item(api_key: Optional[str] = Security(api_key_header)):
    """
    Returns a JSON representing the given user via the provided ID.
    Does not return the _id ObjectID, as this is for internal mongo purposes.
    - return: JSON string
    """
    collection = db[api_key]
    ret = collection.find_one({"inuse": False})
    ret.pop("_id")
    return ret


# GET /api/?query&query {json} # "Get Query"
@app.get("/api/search/")
def query_item(limit: int = 10,
                inuse: Optional[bool] = None,
                serial: Optional[int] = None,
                notes: Optional[str] = None,
                name: Optional[str] = None,
                contents: Optional[list] = None,
                api_key: Optional[str] = Security(api_key_header)
               ):
    collection = db[api_key]
    query = {}
    if inuse is not None:
        query.update({f"inuse": inuse})
    if serial is not None:
        query.update({f"serial": serial})
    if notes is not None:
        query.update({f"notes": notes})
    if name is not None:
        query.update({f"name": name})
    if contents is not None:
        query.update({f"contents": contents})
    ret = [elem for elem in collection.find(query, limit=limit)]
    [elem.pop("_id") for elem in ret]
    return ret


# PUT /api/code {json} # "Enable New Box, Set Notes"
@app.put("/api/{item_code}")
def put_item(item_code: str, asset: EditableAsset, api_key: Optional[str] = Security(api_key_header)):
    collection = db[api_key]
    collection.update_one({"code": item_code},
                          {"$set": {"notes": asset.notes, "contents": asset.contents, "inuse": asset.inuse}})
    ret = collection.find_one({"code": item_code})
    ret.pop("_id")
    return ret


# DELETE /api/code # "De-activate Existing Box"
@app.delete("/api/{item_code}")
def delete_item(item_code: str, response: Response, api_key: Optional[str] = Security(api_key_header)):
    collection = db[api_key]
    collection.update_one({"code": item_code}, {"$set": {"inuse": False}})
    response.status_code = status.HTTP_200_OK
    ret = collection.find_one({"code": item_code})
    ret.pop("_id")
    return ret


# GET /api/code/label-photo # "Get Existing Box Label Photo"
@app.get("/api/{item_code}/label-photo")
def get_label_photo(item_code: str, api_key: Optional[str] = Security(api_key_header)):
    """
    Returns a JSON representing the given user via the provided ID.
    Does not return the _id ObjectID, as this is for internal mongo purposes.
    - param item_code: item code
    - return: Byte object image of label
    """
    if item_code is None or not item_code:
        raise HTTPException(status_code=404, detail="Invalid/Empty query")
    collection = db[api_key]
    ret = collection.find_one({"code": item_code})
    ret.pop("_id")
    filename, image = gen_label(ret, api_key)
    image.save(filename, quality=100)
    return FileResponse(filename)


# DELETE /api/code/label-photo # "Get Existing Box Label Photo"
@app.delete("/api/{item_code}/label-photo")
def delete_label_photo(item_code: str, api_key: Optional[str] = Security(api_key_header)):
    """
    Returns a JSON representing the given user via the provided ID.
    Does not return the _id ObjectID, as this is for internal mongo purposes.
    - param item_code: item code
    - return: Byte object image of label
    """
    os.remove(f"generated-labels/{api_key}-{item_code}.png")


# GET /api/code/labels-pdf # "Get labels for list of codes "
@app.post("/api/labels-pdf")
def get_labels_pdf(item_codes: list, api_key: Optional[str] = Security(api_key_header)):
    """
    "Get labels for list of codes "
    - param item_code: list of item codes
    - return: Bytes object of PDF
    """
    if item_codes is None or item_codes[0] is None or not item_codes:
        raise HTTPException(status_code=404, detail="Invalid query.")
    collection = db[api_key]
    # GENERATE ALL LABELS IN LIST
    labels = list()
    for item_code in item_codes:
        ret = collection.find_one({"code": item_code})
        ret.pop("_id")
        filename, image = gen_label(ret, api_key)
        image.save(filename, quality=100)
        labels.append(filename)  # 0 is filename, 1 is image in memory
    labels_iter = iter(labels)
    # MAKE PDF OF LABELS
    pdf_filename = f"generated-pdfs/{api_key}.pdf"
    doc = SimpleDocTemplate(pdf_filename, pagesize=LETTER,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=18)
    Story = []
    data = list()
    table_style = [
        # ('GRID', (0, 1), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 1), (1, -1), 'CENTER')
    ]
    Story.append(Spacer(0.25 * inch, 0.25 * inch))
    Story.append(Paragraph(f"This is an auto generated document."))
    Story.append(Spacer(0.25 * inch, 0.25 * inch))
    while True:
        try:
            row = list()
            for i in range(0, 4):
                if len(labels) < 2:
                    entry = labels[0]
                    entry = next(labels_iter)
                    canvas = (platyImage(entry, width=LABEL_SIZE[0] / 6, height=LABEL_SIZE[1] / 5.5, hAlign=1),
                              Spacer(0.1 * inch, 0.1 * inch),
                              )
                    row.append(canvas)
                    print("one entry")
                    raise StopIteration
                else:
                    entry = next(labels_iter)
                    canvas = (platyImage(entry, width=LABEL_SIZE[0]/6, height=LABEL_SIZE[1]/5.5, hAlign=1),
                              Spacer(0.1 * inch, 0.1 * inch),
                              )
                    row.append(canvas)
            data.append(row)
        except StopIteration:
            data.append(row)
            break
    t = Table(data)
    t.setStyle(table_style)
    Story.append(t)
    doc.build(Story)
    return FileResponse(pdf_filename, filename=f"{api_key}.pdf")


# DELETE /api/code/label-photo # "Get Existing Box Label Photo"
@app.delete("/api/labels-pdf")
def delete_labels_pdf(api_key: Optional[str] = Security(api_key_header)):
    """
    Deletes a previously generated pdf. Each api key only can have one pdf in cache.
    """
    os.remove(f"generated-pdfs/{api_key}.pdf")


# GET /api/code/labels-zip # "Get zip of label photos"
@app.post("/api/{item_code}/labels-zip")
def get_labels_zip(item_codes: list, api_key: Optional[str] = Security(api_key_header)):
    """
    Get a zip file containing images of labels of requested item codes.
    Each api key only can have one pdf in cache.
    - param item_code: list of item codes
    - return: Byte object zip of images of labels
    """
    if item_codes is None or item_codes[0] is None or not item_codes:
        raise HTTPException(status_code=404, detail="Invalid query.")
    collection = db[api_key]
    filenames = list()
    zip_filename = f"generated-zips/{api_key}.zip"
    for item_code in item_codes:
        ret = collection.find_one({"code": item_code})
        ret.pop("_id")
        filename, image = gen_label(ret, api_key)
        image.save(filename, quality=100)
        filenames.append(filename)  # 0 is filename, 1 is image in memory
    with ZipFile(zip_filename, 'w') as zip:
        for filename in filenames:
            zip.write(filename)


    filename = f"generated-zips/{api_key}.zip"
    return FileResponse(filename, filename=f"{api_key}.zip")


# DELETE /api/code/label-photo # "Get Existing Box Label Photo"
@app.delete("/api/{item_code}/labels-zip")
def delete_labels_zip(api_key: Optional[str] = Security(api_key_header)):
    """
    Deleted zip file associated with api key.
    Each api key only can have one pdf in cache.
    """
    os.remove(f"generated-zips/{api_key}.zip")

# ----------USERS------------------
# GET /api/users  {json, no api key} # "Get api key for username/password. Essentially is a login"
@app.get("/api/user/")
def get_user(response: Response, username: Optional[str] = Header(None), password: Optional[str] = Header(None)):
    try:
        # Check if user exists
        username = username.lower()
        assert db.command({"usersInfo": username})["users"]
        # Hash username using password, check if collection exists
        key = get_apikey(username=username, password=password)
        assert key in db.collection_names()
        return {"X-API-KEY": key}
    except AssertionError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return response


# # POST /api/users  {json, no api key} # "Create new user,collection, role, return api key"
@app.post("/api/user/")
def post_user(response: Response, username: Optional[str] = Header(None), password: Optional[str] = Header(None)):
    ret_dict = dict()
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
    # !FUTURE update to use programatic generation
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

# # DELETE /api/users  {admin api key} # "Delete user, collection, and role"
@app.delete("/api/user/")
def delete_user(response: Response, username: Optional[str] = Header(None), password: Optional[str] = Header(None)):
    # !FUTURE check for admin api key
    try:
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


if __name__ == "__main__":
    uvicorn.run("main:app", log_level="info")