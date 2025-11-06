# import os
# import zipfile
# import tempfile
# from urllib.parse import urlparse
# import json

# import requests
# import msal
# import pandas as pd

# from django.views.decorators.csrf import csrf_exempt
# from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, FileResponse
# from django.views.decorators.http import require_GET
# from django.conf import settings
# from datetime import datetime
# from zoneinfo import ZoneInfo

# from .models import ProjectData, Message
# from urllib.parse import quote
# import base64
# import io
# from io import BytesIO

# # -------------------------------
# # Azure / OneDrive Configuration
# # -------------------------------

# AZ_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
# AZ_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
# AZ_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
# DEFAULT_SP_SITE = os.environ.get("SP_SITE_URL") 


# # -------------------------------
# # Helper Functions (OneDrive)
# # -------------------------------
# def get_access_token():
#     authority = f"https://login.microsoftonline.com/{AZ_TENANT_ID}"
#     app = msal.ConfidentialClientApplication(
#         AZ_CLIENT_ID,
#         authority=authority,
#         client_credential=AZ_CLIENT_SECRET,
#     )
#     result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
#     if "access_token" in result:
#         return result["access_token"]
#     else:
#         err = result.get("error_description") or result
#         raise Exception(f"Could not obtain token: {err}")


# def get_site_id(access_token, site_url):
#     parsed = urlparse(site_url)
#     hostname = parsed.netloc
#     path = parsed.path
#     endpoint = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{path}"
#     headers = {"Authorization": f"Bearer {access_token}"}
#     resp = requests.get(endpoint, headers=headers)
#     resp.raise_for_status()
#     return resp.json()["id"]


# def create_upload_session(token, site_id, remote_path):
#     """
#     remote_path must include the filename at the end.
#     Example: 'ProjectA/file1.xlsx'
#     """
#     safe_path = quote(remote_path, safe="/")
#     url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_path}:/createUploadSession"
#     headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#     data = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
#     response = requests.post(url, headers=headers, json=data)
#     if response.status_code not in (200, 201):
#         raise Exception(f"Failed to create upload session: {response.status_code} {response.text}")
#     return response.json()["uploadUrl"]


# def stream_upload(upload_url, fileobj, total_size, chunk_size=10 * 1024 * 1024):
#     start = 0
#     while True:
#         chunk = fileobj.read(chunk_size)
#         if not chunk:
#             break
#         end = start + len(chunk) - 1
#         headers = {
#             "Content-Range": f"bytes {start}-{end}/{total_size}",
#             "Content-Length": str(len(chunk)),
#             "Content-Type": "application/octet-stream",
#         }
#         r = requests.put(upload_url, data=chunk, headers=headers)
#         if r.status_code in (200, 201):
#             return r.json()
#         elif r.status_code == 202:
#             start = end + 1
#             continue
#         else:
#             raise Exception(f"Upload failed: status {r.status_code}, body: {r.text}")


# # -------------------------------
# # Main Upload View
# # -------------------------------
# @csrf_exempt
# def upload_zip(request):
#     if request.method != "POST":
#         return HttpResponse("Use POST", status=400)

#     uploaded_file = request.FILES.get("file")
#     if not uploaded_file:
#         return HttpResponseBadRequest("Missing file field")

#     project_name = os.path.splitext(uploaded_file.name)[0]  # Remove .zip extension
#     site_url = request.POST.get("site_url", DEFAULT_SP_SITE)
#     if not site_url:
#         return HttpResponseBadRequest("Missing site_url and SP_SITE_URL not set")

#     dest_path = request.POST.get("dest_path", "").strip("/")

#     try:
#         # -----------------------
#         # Step 1: Extract ZIP
#         # -----------------------
#         with tempfile.TemporaryDirectory() as temp_dir:
#             zip_path = (
#                 uploaded_file.temporary_file_path()
#                 if hasattr(uploaded_file, "temporary_file_path")
#                 else os.path.join(temp_dir, uploaded_file.name)
#             )
#             if not hasattr(uploaded_file, "temporary_file_path"):
#                 with open(zip_path, "wb") as f:
#                     for chunk in uploaded_file.chunks():
#                         f.write(chunk)

#             with zipfile.ZipFile(zip_path, "r") as zip_ref:
#                 zip_ref.extractall(temp_dir)

#             # -----------------------
#             # Step 2: Find Excel
#             # -----------------------
#             excel_file = None
#             for root, dirs, files in os.walk(temp_dir):
#                 for file in files:
#                     if file.endswith((".xlsx", ".xls")):
#                         excel_file = os.path.join(root, file)
#                         break
#                 if excel_file:
#                     break

#             # -----------------------
#             # Step 3: Parse Excel & Store DB
#             # -----------------------
#             if excel_file:
#                 df = pd.read_excel(excel_file)
#                 for _, row in df.iterrows():
#                     if pd.isna(row.iloc[1]) or str(row.iloc[1]).strip() == "":
#                         break
#                     part_no = str(row.iloc[1]).strip()
#                     description = str(row.iloc[2]).strip()
#                     raw_qty = row.iloc[3]
#                     try:
#                         quantity = int(float(raw_qty)) if pd.notna(raw_qty) else 0
#                     except (ValueError, TypeError):
#                         quantity = 0

#                     # Update or create (overwrite)
#                     ProjectData.objects.update_or_create(
#                         project_name=project_name,
#                         part_no=part_no,
#                         defaults={
#                             "description": description,
#                             "quantity": quantity,
#                         }
#                     )
#             else:
#                 # -----------------------
#                 # NEW: Handle case when no Excel found
#                 # -----------------------
#                 for root, dirs, files in os.walk(temp_dir):
#                     for file_name in files:
#                         if file_name == uploaded_file.name:
#                             continue
#                         part_no = os.path.splitext(file_name)[0]
#                         description = ""
#                         quantity = 1

#                         ProjectData.objects.update_or_create(
#                             project_name=project_name,
#                             part_no=part_no,
#                             defaults={
#                                 "description": description,
#                                 "quantity": quantity,
#                             }
#                         )
                    

#             # -----------------------
#             # Step 4: Upload all files as folder to OneDrive (fixed)
#             # -----------------------
#             token = get_access_token()
#             site_id = get_site_id(token, site_url)

#             # Build full folder path on OneDrive (preserve dest_path if provided)
#             if dest_path:
#                 full_folder_path = f"{dest_path}/{project_name}"
#             else:
#                 full_folder_path = project_name

#             # Encode path but keep slashes
#             safe_folder_path = quote(full_folder_path, safe="/")

#             # Create folder endpoint: PUT to .../drive/root:/{path}:
#             folder_endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_folder_path}:"
#             headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#             # Try create (PUT). If it already exists Graph will return 200/201, otherwise it creates.
#             create_folder_resp = requests.put(folder_endpoint, headers=headers, json={"folder": {}})
#             if create_folder_resp.status_code not in (200, 201):
#                 # Provide the response text for debugging if it fails
#                 raise Exception(f"Failed to create folder: {create_folder_resp.status_code} {create_folder_resp.text}")

#             # Walk extracted files and upload each preserving relative structure
#             uploaded_files = []
#             for root, dirs, files in os.walk(temp_dir):
#                 for file_name in files:
#                     if file_name == uploaded_file.name:
#                         continue
#                     local_path = os.path.join(root, file_name)

#                     # All files directly under main folder
#                     remote_path = f"{full_folder_path}/{file_name}"

#                     upload_url = create_upload_session(token, site_id, remote_path)

#                     with open(local_path, "rb") as f:
#                         total_size = os.path.getsize(local_path)
#                         result = stream_upload(upload_url, f, total_size)
#                         item_id = result.get("id") if isinstance(result, dict) else None
#                         uploaded_files.append({
#                             "name": file_name,
#                             "id": item_id
#                         })



#         return JsonResponse({
#             "status": "ok",
#             "folder": full_folder_path,
#             "uploaded_files": uploaded_files
#         })

#     except Exception as e:
#         return JsonResponse({"status": "error", "error": str(e)}, status=500)

# # -------------------------------
# # Fetch Data View
# # -------------------------------
# @csrf_exempt
# @require_GET
# def fetch_data(request):
#     """
#     GET params:
#       - project_name (optional)
#       - part_no (optional)
#     """
#     project_name = request.GET.get("project_name")
#     part_no = request.GET.get("part_no")

#     query = ProjectData.objects.all()
#     if project_name:
#         query = query.filter(project_name=project_name)
#     if part_no:
#         query = query.filter(part_no=part_no)

#     data = [
#         {
#             "project_name": r.project_name,
#             "part_no": r.part_no,
#             "description": r.description,
#             "quantity": r.quantity,
#             "mat": r.mat,
#             "vmc": r.vmc,
#             "cnc": r.cnc,
#             "hand": r.hand,
#             "laser": r.laser,
#             "bend": r.bend,
#             "weld": r.weld,
#             "ext": r.ext,
#             "profit": r.profit,
#             "unit": r.unit,
#             "total": r.total,
#             "grand_total" : r.grand_total,
#             "quotation_name" : r.quotation_name
#         }
#         for r in query
#     ]
    

#     return JsonResponse({"status": "ok", "data": data})
# @csrf_exempt
# def update_cost(request):
#     """
#     POST JSON:
#     {
#         "project_name": "filename.zip",
#         "part_no": "PART123",
#         "mat": 100,
#         "vmc": 200,
#         "cnc": 150,
#         ...
#     }
#     Only fields provided will be updated; others remain unchanged.
#     """
#     if request.method != "POST":
#         return JsonResponse({"status": "error", "error": "Use POST"}, status=400)

#     try:
#         data = json.loads(request.body)
#         project_name = data.get("project_name")
#         part_no = data.get("part_no")

#         if not project_name or not part_no:
#             return JsonResponse({"status": "error", "error": "project_name and part_no required"}, status=400)

#         obj = ProjectData.objects.get(project_name=project_name, part_no=part_no)

#         # Update only fields present in request
#         cost_fields = ["mat", "vmc", "cnc", "hand", "laser", "bend", "weld", "ext", "profit", "unit", "total", "grand_total", "quotation_name"]
#         for field in cost_fields:
#             if field in data:
#                 setattr(obj, field, data[field])

#         obj.save()
#         return JsonResponse({"status": "ok", "message": "Cost fields updated successfully"})

#     except ProjectData.DoesNotExist:
#         return JsonResponse({"status": "error", "error": "Part not found in this project"}, status=404)
#     except Exception as e:
#         return JsonResponse({"status": "error", "error": str(e)}, status=500)

# #fecth the files from onedrive 

# @csrf_exempt
# @require_GET
# def list_zip_files(request):
#     """
#     Fetch list of ZIP files stored in the OneDrive folder.
#     Optional query param: dest_path
#     """
#     try:
#         dest_path = request.GET.get("dest_path", "").strip("/")
#         site_url = request.GET.get("site_url", DEFAULT_SP_SITE)

#         if not site_url:
#             return JsonResponse({"status": "error", "error": "Missing site_url and SP_SITE_URL not set"}, status=400)

#         # Authenticate
#         token = get_access_token()
#         site_id = get_site_id(token, site_url)

#         # Build endpoint: list files in folder
#         if dest_path:
#             endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{dest_path}:/children"
#         else:
#             endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/children"

#         headers = {"Authorization": f"Bearer {token}"}
#         resp = requests.get(endpoint, headers=headers)
#         resp.raise_for_status()
#         items = resp.json().get("value", [])

#         # Filter only ZIP files
#         zip_files = []
#         for item in items:
#             if "folder" in item:  # You may want to filter ZIPs by extension instead
#                 utc_time_str = item.get("createdDateTime")
#                 if utc_time_str:
#                     # Convert to IST
#                     utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
#                     utc_time = utc_time.replace(tzinfo=ZoneInfo("UTC"))
#                     ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
#                     uploaded_at = ist_time.strftime("%Y-%m-%d %H:%M:%S")  # nice readable format
#                 else:
#                     uploaded_at = None

#                 zip_files.append({
#                     "name": item["name"],
#                     "id": item["id"],
#                     "size": item["size"],
#                     "uploaded_at": uploaded_at
#                 })

#         return JsonResponse({"status": "ok", "files": zip_files})

#     except Exception as e:
#         return JsonResponse({"status": "error", "error": str(e)}, status=500)
        

# @csrf_exempt
# def download_project_zip(request, project_name):
#     """
#     Fetch ZIP file from OneDrive by project_name and return it as a downloadable file.
#     """
#     try:
#         # -----------------------
#         # Step 1: Fetch OneDrive file metadata
#         # -----------------------
#         token = get_access_token()
#         site_id = get_site_id(token, DEFAULT_SP_SITE)
#         endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/children"
#         headers = {"Authorization": f"Bearer {token}"}
#         resp = requests.get(endpoint, headers=headers)
#         resp.raise_for_status()
#         items = resp.json().get("value", [])

#         # Find the file
#         file_item = next((i for i in items if i["name"] == project_name), None)
#         if not file_item:
#             return JsonResponse({"status": "error", "error": "File not found on OneDrive"}, status=404)

#         # -----------------------
#         # Step 2: Download ZIP file content
#         # -----------------------
#         download_url = file_item["@microsoft.graph.downloadUrl"]
#         zip_resp = requests.get(download_url)
#         zip_resp.raise_for_status()

#         # Wrap content in BytesIO so it can be sent as a file-like object
#         zip_bytes = BytesIO(zip_resp.content)

#         # -----------------------
#         # Step 3: Return as FileResponse
#         # -----------------------
#         response = FileResponse(zip_bytes, as_attachment=True, filename=project_name)
#         return response

#     except Exception as e:
#         return JsonResponse({"status": "error", "error": str(e)}, status=500)
    
# @csrf_exempt
# @require_GET
# def fetch_all_files(request, project_name):
#     try:
#         token = get_access_token()
#         site_id = get_site_id(token, DEFAULT_SP_SITE)
#         endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{project_name}:/children"
#         headers = {"Authorization": f"Bearer {token}"}
#         resp = requests.get(endpoint, headers=headers)
#         resp.raise_for_status()
#         items = resp.json().get("value", [])

#         files = []
#         for item in items:
#             if "@microsoft.graph.downloadUrl" in item:
#                 files.append({
#                     "name": item["name"],
#                     "url": item["@microsoft.graph.downloadUrl"]
#                 })

#         return JsonResponse({"status": "ok", "files": files})
#     except Exception as e:
#         return JsonResponse({"status": "error", "error": str(e)}, status=500)



# @csrf_exempt
# def quote_name(request):
#     if request.method == 'POST':
#         text = request.POST.get('text')
#         if text:
#             # Get or create the single message entry
#             message, created = Message.objects.get_or_create(id=1, defaults={'text': text})
            
#             if not created:
#                 message.text = text
#                 message.save()
            
#             return JsonResponse({'status': 'success', 'message': 'Saved/Updated'})
        
#         return JsonResponse({'status': 'error', 'message': 'No text provided'})
    
#     return JsonResponse({'status': 'error', 'message': 'Invalid request'})


# @csrf_exempt
# def get_quote(request):
#     try:
#         message = Message.objects.values('id', 'text').get(id=1)
#         return JsonResponse(message)
#     except Message.DoesNotExist:
#         return JsonResponse({'error': 'Message not found'}, status=404)


import os
import zipfile
import tempfile
from urllib.parse import urlparse
import json

import requests
import msal
import pandas as pd

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, FileResponse
from django.views.decorators.http import require_GET
from django.conf import settings
from datetime import datetime
from zoneinfo import ZoneInfo
from django.utils import timezone

from .models import ProjectData, Message, DashboardData
from urllib.parse import quote
import base64
import io
from io import BytesIO

# -------------------------------
# Azure / OneDrive Configuration
# -------------------------------

AZ_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZ_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZ_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
DEFAULT_SP_SITE = os.environ.get("SP_SITE_URL") 


# -------------------------------
# Helper Functions (OneDrive)
# -------------------------------
def get_access_token():
    authority = f"https://login.microsoftonline.com/{AZ_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        AZ_CLIENT_ID,
        authority=authority,
        client_credential=AZ_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        return result["access_token"]
    else:
        err = result.get("error_description") or result
        raise Exception(f"Could not obtain token: {err}")


def get_site_id(access_token, site_url):
    parsed = urlparse(site_url)
    hostname = parsed.netloc
    path = parsed.path
    endpoint = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(endpoint, headers=headers)
    resp.raise_for_status()
    return resp.json()["id"]


def create_upload_session(token, site_id, remote_path):
    """
    remote_path must include the filename at the end.
    Example: 'ProjectA/file1.xlsx'
    """
    safe_path = quote(remote_path, safe="/")
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_path}:/createUploadSession"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code not in (200, 201):
        raise Exception(f"Failed to create upload session: {response.status_code} {response.text}")
    return response.json()["uploadUrl"]


def stream_upload(upload_url, fileobj, total_size, chunk_size=10 * 1024 * 1024):
    start = 0
    while True:
        chunk = fileobj.read(chunk_size)
        if not chunk:
            break
        end = start + len(chunk) - 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{total_size}",
            "Content-Length": str(len(chunk)),
            "Content-Type": "application/octet-stream",
        }
        r = requests.put(upload_url, data=chunk, headers=headers)
        if r.status_code in (200, 201):
            return r.json()
        elif r.status_code == 202:
            start = end + 1
            continue
        else:
            raise Exception(f"Upload failed: status {r.status_code}, body: {r.text}")


# -------------------------------
# Main Upload View
# -------------------------------
@csrf_exempt
def upload_zip(request):
    if request.method != "POST":
        return HttpResponse("Use POST", status=400)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return HttpResponseBadRequest("Missing file field")

    project_name = os.path.splitext(uploaded_file.name)[0]  # Remove .zip extension
    site_url = request.POST.get("site_url", DEFAULT_SP_SITE)
    if not site_url:
        return HttpResponseBadRequest("Missing site_url and SP_SITE_URL not set")

    dest_path = request.POST.get("dest_path", "").strip("/")

    try:
        # -----------------------
        # Step 1: Extract ZIP
        # -----------------------
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = (
                uploaded_file.temporary_file_path()
                if hasattr(uploaded_file, "temporary_file_path")
                else os.path.join(temp_dir, uploaded_file.name)
            )
            if not hasattr(uploaded_file, "temporary_file_path"):
                with open(zip_path, "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # -----------------------
            # Step 2: Find Excel
            # -----------------------
            excel_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith((".xlsx", ".xls")):
                        excel_file = os.path.join(root, file)
                        break
                if excel_file:
                    break

            # -----------------------
            # Step 3: Parse Excel & Store DB
            # -----------------------
            # if excel_file:
            #     df = pd.read_excel(excel_file)
            #     for _, row in df.iterrows():
            #         if pd.isna(row.iloc[1]) or str(row.iloc[1]).strip() == "":
            #             continue  # Skip empty rows
            #         part_no = str(row.iloc[1]).strip()
            #         description = str(row.iloc[2]).strip()
            #         raw_qty = row.iloc[3]
            #         try:
            #             quantity = int(float(raw_qty)) if pd.notna(raw_qty) else 0
            #         except (ValueError, TypeError):
            #             quantity = 0

            #         # Update or create ProjectData
            #         obj, _ = ProjectData.objects.update_or_create(
            #             project_name=project_name,
            #             part_no=part_no,
            #             defaults={
            #                 "description": description,
            #                 "quantity": quantity,
            #             }
            #         )

            #         # Sync DashboardData
            #         DashboardData.objects.update_or_create(
            #             projectName=project_name,
            #             defaults={
            #                 "quotationname": "",
            #                 "grandTotal": 0,
            #             }
            #         )
            if excel_file:
                df = pd.read_excel(excel_file)
                for _, row in df.iterrows():
                    first_col = row.iloc[0]

                    # ✅ Skip rows where 0th column (S.NO.) is empty or NaN
                    if pd.isna(first_col) or str(first_col).strip() == "":
                        continue

                    # ✅ Skip if PART NO column is empty
                    if pd.isna(row.iloc[1]) or str(row.iloc[1]).strip() == "":
                        continue

                    part_no = str(row.iloc[1]).strip()
                    description = str(row.iloc[2]).strip()
                    raw_qty = row.iloc[3]

                    try:
                        quantity = int(float(raw_qty)) if pd.notna(raw_qty) else 0
                    except (ValueError, TypeError):
                        quantity = 0

                    # ✅ Update or create ProjectData
                    obj, _ = ProjectData.objects.update_or_create(
                        project_name=project_name,
                        part_no=part_no,
                        defaults={
                            "description": description,
                            "quantity": quantity,
                        }
                    )

                    # ✅ Sync DashboardData (once per project)
                    DashboardData.objects.update_or_create(
                        projectName=project_name,
                        defaults={
                            "quotationname": "",
                            "grandTotal": 0,
                        }
                    )

            else:
                # Handle case when no Excel found: create ProjectData from file names
                for root, dirs, files in os.walk(temp_dir):
                    for file_name in files:
                        if file_name == uploaded_file.name:
                            continue
                        part_no = os.path.splitext(file_name)[0]
                        description = ""
                        quantity = 1

                        obj, _ = ProjectData.objects.update_or_create(
                            project_name=project_name,
                            part_no=part_no,
                            defaults={
                                "description": description,
                                "quantity": quantity,
                            }
                        )

                        # Sync DashboardData
                        DashboardData.objects.update_or_create(
                            projectName=project_name,
                            defaults={
                                "quotationname": "",
                                "grandTotal":0,
                                
                            }
                        )

            # -----------------------
            # Step 4: Upload all files to OneDrive
            # -----------------------
            token = get_access_token()
            site_id = get_site_id(token, site_url)
            full_folder_path = f"{dest_path}/{project_name}" if dest_path else project_name
            safe_folder_path = quote(full_folder_path, safe="/")

            # Create folder
            folder_endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_folder_path}:"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            create_folder_resp = requests.put(folder_endpoint, headers=headers, json={"folder": {}})
            if create_folder_resp.status_code not in (200, 201):
                raise Exception(f"Failed to create folder: {create_folder_resp.status_code} {create_folder_resp.text}")

            # Upload files
            uploaded_files = []
            for root, dirs, files in os.walk(temp_dir):
                for file_name in files:
                    if file_name == uploaded_file.name:
                        continue
                    local_path = os.path.join(root, file_name)
                    remote_path = f"{full_folder_path}/{file_name}"
                    upload_url = create_upload_session(token, site_id, remote_path)
                    with open(local_path, "rb") as f:
                        total_size = os.path.getsize(local_path)
                        result = stream_upload(upload_url, f, total_size)
                        item_id = result.get("id") if isinstance(result, dict) else None
                        uploaded_files.append({
                            "name": file_name,
                            "id": item_id
                        })

        return JsonResponse({
            "status": "ok",
            "folder": full_folder_path,
            "uploaded_files": uploaded_files
        })

    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


# -------------------------------
# Fetch Data View
# -------------------------------
@csrf_exempt
@require_GET
def fetch_data(request):
    """
    GET params:
      - project_name (optional)
      - part_no (optional)
    """
    project_name = request.GET.get("project_name")
    part_no = request.GET.get("part_no")

    query = ProjectData.objects.all()
    if project_name:
        query = query.filter(project_name=project_name)
    if part_no:
        query = query.filter(part_no=part_no)

    data = [
        {
            "project_name": r.project_name,
            "part_no": r.part_no,
            "description": r.description,
            "mat": r.mat,
            "vmc": r.vmc,
            "cnc": r.cnc,
            "hand": r.hand,
            "laser": r.laser,
            "bend": r.bend,
            "weld": r.weld,
            "ext": r.ext,
            "quantity": r.quantity,
            "profit": r.profit,
            "unit": r.unit,
            "total": r.total,
        }
        for r in query
    ]
    

    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
def update_cost(request):
    """
    Accepts either:
    - A single JSON object, or
    - A list of JSON objects

    Example single:
    {
        "project_name": "new",
        "part_no": "601-2-14439",
        "mat": 120
    }

    Example multiple:
    [
        {...}, {...}
    ]
    """

    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Use POST"}, status=400)

    try:
        data = json.loads(request.body)

        # If a single object is passed, convert it to a list
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            return JsonResponse({
                "status": "error",
                "error": "Invalid JSON format — expected an object or a list of objects"
            }, status=400)

        cost_fields = [
            "mat", "vmc", "cnc", "hand", "laser", "bend", "weld", "ext",
            "profit", "unit", "total", "grand_total", "quotation_name"
        ]

        results = []

        for entry in data:
            project_name = entry.get("project_name")
            part_no = entry.get("part_no")

            if not project_name or not part_no:
                results.append({
                    "part_no": part_no,
                    "status": "error",
                    "error": "project_name and part_no required"
                })
                continue

            try:
                obj = ProjectData.objects.get(project_name=project_name, part_no=part_no)

                for field in cost_fields:
                    if field in entry:
                        setattr(obj, field, entry[field])

                obj.save()

                results.append({
                    "part_no": part_no,
                    "status": "ok",
                    "message": "Updated successfully"
                })

            except ProjectData.DoesNotExist:
                results.append({
                    "part_no": part_no,
                    "status": "error",
                    "error": "Part not found in this project"
                })
            except Exception as e:
                results.append({
                    "part_no": part_no,
                    "status": "error",
                    "error": str(e)
                })

        return JsonResponse({
            "status": "ok",
            "results": results
        })

    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)



#fecth the files from onedrive 

@csrf_exempt
@require_GET
def list_zip_files(request):
    """
    Fetch list of ZIP files stored in the OneDrive folder.
    Optional query param: dest_path
    """
    try:
        dest_path = request.GET.get("dest_path", "").strip("/")
        site_url = request.GET.get("site_url", DEFAULT_SP_SITE)

        if not site_url:
            return JsonResponse({"status": "error", "error": "Missing site_url and SP_SITE_URL not set"}, status=400)

        # Authenticate
        token = get_access_token()
        site_id = get_site_id(token, site_url)

        # Build endpoint: list files in folder
        if dest_path:
            endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{dest_path}:/children"
        else:
            endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/children"

        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(endpoint, headers=headers)
        resp.raise_for_status()
        items = resp.json().get("value", [])

        # Filter only ZIP files
        zip_files = []
        for item in items:
            if "folder" in item:  # You may want to filter ZIPs by extension instead
                utc_time_str = item.get("createdDateTime")
                if utc_time_str:
                    # Convert to IST
                    utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
                    utc_time = utc_time.replace(tzinfo=ZoneInfo("UTC"))
                    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
                    uploaded_at = ist_time.strftime("%Y-%m-%d %H:%M:%S")  # nice readable format
                else:
                    uploaded_at = None

                zip_files.append({
                    "name": item["name"],
                    "id": item["id"],
                    "size": item["size"],
                    "uploaded_at": uploaded_at
                })

        return JsonResponse({"status": "ok", "files": zip_files})

    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)
        

@csrf_exempt
@require_GET
def fetch_all_files(request, project_name):
    try:
        token = get_access_token()
        site_id = get_site_id(token, DEFAULT_SP_SITE)
        endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{project_name}:/children"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(endpoint, headers=headers)
        resp.raise_for_status()
        items = resp.json().get("value", [])

        files = []
        for item in items:
            if "@microsoft.graph.downloadUrl" in item:

                # Skip Excel files
                if item["name"].lower().endswith((".xlsx", ".xls")):
                    continue

                files.append({
                    "name": item["name"],
                    "url": item["@microsoft.graph.downloadUrl"]
                })

        return JsonResponse({"status": "ok", "files": files})
    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def quote_name(request):
    if request.method == 'POST':
        text = request.POST.get('text')
        if text:
            # Get or create the single message entry
            message, created = Message.objects.get_or_create(id=1, defaults={'text': text})
            
            if not created:
                message.text = text
                message.save()
            
            return JsonResponse({'status': 'success', 'message': 'Saved/Updated'})
        
        return JsonResponse({'status': 'error', 'message': 'No text provided'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})


@csrf_exempt
def get_quote(request):
    try:
        message = Message.objects.values('id', 'text').get(id=1)
        return JsonResponse(message)
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Message not found'}, status=404)


@csrf_exempt
def get_dashboard_data(request):
    project_name = request.GET.get('projectName') or request.POST.get('projectName')

    if project_name:
        data = list(DashboardData.objects.filter(projectName=project_name)
                    .values('projectName', 'quotationname', 'grandTotal', 'last_date'))
    else:
        data = list(DashboardData.objects.values('projectName', 'quotationname', 'grandTotal', 'last_date'))

    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
def update_dashboard(request):
    """
    POST JSON example:
    {
        "projectName": "702-1-05180 - MFG",
        "quotationname": "QTN-001",
        "grandTotal": 54200
    }
    Creates or updates a DashboardData record.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Use POST method"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))

        project_name = data.get("projectName")
        quotation_name = data.get("quotationname")
        grand_total = data.get("grandTotal")

        if not project_name:
            return JsonResponse({"status": "error", "error": "projectName is required"}, status=400)

        # Create or update the record
        dashboard, created = DashboardData.objects.update_or_create(
            projectName=project_name,
            defaults={
                "quotationname": quotation_name,
                "grandTotal": grand_total,
                "last_date": timezone.now(),  # optional — model already updates it on save
            }
        )

        action = "created" if created else "updated"

        return JsonResponse({
            "status": "ok",
            "message": f"DashboardData {action} successfully",
            "data": {
                "projectName": dashboard.projectName,
                "quotationname": dashboard.quotationname,
                "grandTotal": dashboard.grandTotal,
                "last_date": dashboard.last_date.strftime("%Y-%m-%d %H:%M:%S"),
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)



# -------------------------------
# Data Fetch for Pricelist
# -------------------------------

@csrf_exempt
@require_GET
def price_list_fetch(request):
    data = list(ProjectData.objects.values("project_name", "part_no", "unit"))
    return JsonResponse({"status": "ok", "data": data})
