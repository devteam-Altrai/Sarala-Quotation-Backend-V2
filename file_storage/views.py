import os
import zipfile
import tempfile
from urllib.parse import urlparse
import json
import shutil
import fitz

import requests
import msal
import pandas as pd

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, FileResponse
from django.core.files.storage import FileSystemStorage
from .utils import whiteout_pdf
from file_storage.file_formatter_utils.vvdn_utils import vvdn_pdf
from file_storage.file_formatter_utils.asm_utils import asm_pdf
from file_storage.file_formatter_utils.sanmina_utils import sanmina_pdf
from file_storage.file_formatter_utils.anora_utils import anora_pdf
from django.views.decorators.http import require_GET
from django.conf import settings

from zoneinfo import ZoneInfo
from django.utils import timezone
# import datetime
from datetime import datetime

from rest_framework.response import Response
from rest_framework import status

from .models import ProjectData, Message, DashboardData, NumberEntry, PoNumber, OrderStatus
from urllib.parse import quote
import base64
import io
from io import BytesIO

from concurrent.futures import ThreadPoolExecutor, as_completed
from rest_framework.decorators import api_view

from .utils import get_financial_year_code,generate_order_serial
import logging


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

    project_name = os.path.splitext(uploaded_file.name)[0]
    site_url = request.POST.get("site_url", DEFAULT_SP_SITE)
    if not site_url:
        return HttpResponseBadRequest("Missing site_url and SP_SITE_URL not set")

    dest_path = request.POST.get("dest_path", "").strip("/")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:

            # Save uploaded zip locally
            zip_path = (
                uploaded_file.temporary_file_path()
                if hasattr(uploaded_file, "temporary_file_path")
                else os.path.join(temp_dir, uploaded_file.name)
            )
            if not hasattr(uploaded_file, "temporary_file_path"):
                with open(zip_path, "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

            # Extract ZIP
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find Excel file if exists
            excel_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith((".xlsx", ".xls")):
                        excel_file = os.path.join(root, file)
                        break
                if excel_file:
                    break

            # Parse Excel → Save DB
            if excel_file:
                df = pd.read_excel(excel_file)

                for _, row in df.iterrows():
                    first_col = row.iloc[0]
                    if pd.isna(first_col) or str(first_col).strip() == "":
                        continue
                    if pd.isna(row.iloc[1]) or str(row.iloc[1]).strip() == "":
                        continue

                    part_no = str(row.iloc[1]).strip()
                    description = str(row.iloc[2]).strip()
                    raw_qty = row.iloc[3]

                    try:
                        quantity = int(float(raw_qty)) if pd.notna(raw_qty) else 0
                    except:
                        quantity = 0

                    ProjectData.objects.update_or_create(
                        project_name=project_name,
                        part_no=part_no,
                        defaults={"description": description, "quantity": quantity}
                    )

                DashboardData.objects.update_or_create(
                    projectName=project_name,
                    defaults={"quotationname": "", "grandTotal": 0, "projectStatus":"PENDING"}
                )

            else:
                # No Excel → Create DB entries from file names
                for root, dirs, files in os.walk(temp_dir):
                    for file_name in files:
                        if file_name == uploaded_file.name:
                            continue
                        part_no = os.path.splitext(file_name)[0]
                        ProjectData.objects.update_or_create(
                            project_name=project_name,
                            part_no=part_no,
                            defaults={"description": "", "quantity": 1}
                        )

                DashboardData.objects.update_or_create(
                    projectName=project_name,
                    defaults={"quotationname": "", "grandTotal": 0, "projectStatus":"PENDING"}
                )

            # OneDrive Upload — now optimized
            token = get_access_token()
            site_id = get_site_id(token, site_url)
            full_folder_path = f"{dest_path}/{project_name}" if dest_path else project_name
            safe_folder_path = quote(full_folder_path, safe="/")

            folder_endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_folder_path}:"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            create_folder_resp = requests.put(folder_endpoint, headers=headers, json={"folder": {}})
            if create_folder_resp.status_code not in (200, 201):
                raise Exception(f"Failed to create folder: {create_folder_resp.status_code} {create_folder_resp.text}")

            # Shared HTTP session for speed
            session = requests.Session()
            session.headers.update({"Authorization": f"Bearer {token}"})

            uploaded_files = []

            def upload_single_file(local_path, remote_path):
                upload_url = create_upload_session(token, site_id, remote_path)
                total_size = os.path.getsize(local_path)
                chunk_size = 5 * 1024 * 1024  # 5 MB

                with open(local_path, "rb") as f:
                    start = 0
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break

                        end = start + len(chunk) - 1
                        headers = {
                            "Content-Range": f"bytes {start}-{end}/{total_size}",
                            "Content-Length": str(len(chunk)),
                            "Content-Type": "application/octet-stream",
                        }
                        r = session.put(upload_url, data=chunk, headers=headers)

                        if r.status_code in (200, 201):
                            result = r.json()
                            return {"name": os.path.basename(local_path), "id": result.get("id")}
                        elif r.status_code == 202:
                            start = end + 1
                            continue
                        else:
                            raise Exception(f"Upload failed: {r.status_code} {r.text}")

            tasks = []
            with ThreadPoolExecutor(max_workers=16) as executor:
                for root, dirs, files in os.walk(temp_dir):
                    for file_name in files:
                        if file_name == uploaded_file.name:
                            continue
                        local_path = os.path.join(root, file_name)
                        remote_path = f"{full_folder_path}/{file_name}"
                        tasks.append(executor.submit(upload_single_file, local_path, remote_path))

                for future in as_completed(tasks):
                    uploaded_files.append(future.result())

        return JsonResponse({"status": "ok", "folder": full_folder_path, "uploaded_files": uploaded_files})

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
    # if project_name:
    #     project_name = project_name.strip()
    #     query = query.filter(project_name__icontains=project_name)
    # if part_no:
    #     part_code = part_no.strip().split()[0]  # take only the first part
    #     query = query.filter(part_no__icontains=part_code)
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
            "po_reference": r.po_reference,
        }
        for r in query
    ]


    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
def update_cost(request):
    """
    Accepts:
    - A single JSON object, or
    - A list of JSON objects

    Only the fields *included* in the payload will be updated.
    """

    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Use POST"}, status=400)

    try:
        data = json.loads(request.body)
        print("RECEIVED PAYLOAD:", data)

        # Normalize to a list
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            return JsonResponse({
                "status": "error",
                "error": "Invalid JSON — expected an object or list of objects"
            }, status=400)

        # Allowed fields for partial update
        allowed_fields = [
            "mat", "vmc", "cnc", "hand", "laser", "bend", "weld", "ext",
            "profit", "unit", "total", "grand_total", "quotation_name","part_status","part_remark","quantity","description","po_reference"
        ]

        results = []

        for entry in data:
            project_name = entry.get("project_name")
            part_no = entry.get("part_no")

            if not project_name or not part_no:
                results.append({
                    "part_no": part_no,
                    "status": "error",
                    "error": "project_name and part_no are required"
                })
                continue

            try:
                obj = ProjectData.objects.get(
                    project_name=project_name,
                    part_no=part_no
                )

                # Update only fields provided in the request
                for field in allowed_fields:
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
                    "error": "Part not found for this project"
                })

            except Exception as e:
                results.append({
                    "part_no": part_no,
                    "status": "error",
                    "error": str(e)
                })

        return JsonResponse({"status": "ok", "results": results})

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
        headers = {
            "Authorization": f"Bearer {token}"
        }

        files = []

        while endpoint:
            resp = requests.get(endpoint, headers=headers)
            resp.raise_for_status()

            data = resp.json()
            items = data.get("value", [])

            for item in items:

                # Check if downloadable file
                if "@microsoft.graph.downloadUrl" not in item:
                    continue

                # Skip Excel files
                if item["name"].lower().endswith((".xlsx", ".xls")):
                    continue

                files.append({
                    "name": item["name"],
                    "url": item["@microsoft.graph.downloadUrl"]
                })

            # Next page URL
            endpoint = data.get("@odata.nextLink")

        return JsonResponse({
            "status": "ok",
            "count": len(files),
            "files": files
        })

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "error": str(e)
        }, status=500)


      

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

#                 # Skip Excel files
#                 if item["name"].lower().endswith((".xlsx", ".xls")):
#                     continue

#                 files.append({
#                     "name": item["name"],
#                     "url": item["@microsoft.graph.downloadUrl"]
#                 })

#         return JsonResponse({"status": "ok", "files": files})
#     except Exception as e:
#         return JsonResponse({"status": "error", "error": str(e)}, status=500)


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
                    .values('projectName', 'quotationname', 'grandTotal', 'projectStatus', 'ext_info', 'last_date'))
    else:
        data = list(DashboardData.objects.values('projectName', 'quotationname', 'grandTotal', 'projectStatus', 'ext_info', 'last_date'))

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
        project_status = data.get("projectStatus")

        if not project_name:
            return JsonResponse({"status": "error", "error": "projectName is required"}, status=400)

        # Create or update the record
        dashboard, created = DashboardData.objects.update_or_create(
            projectName=project_name,
            defaults={
                "quotationname": quotation_name,
                "grandTotal": grand_total,
                "projectStatus": project_status,
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
                "projectStatus": dashboard.projectStatus,
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
    data = list(ProjectData.objects.values("project_name", "part_no", "mat", "vmc", "cnc", "hand", "laser", "bend", "ext", "weld", "unit", "quantity", "profit"))
    return JsonResponse({"status": "ok", "data": data})



@csrf_exempt
def status_detail(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            project_name = data.get("projectName")
            po_number = data.get("po_number")

            if not po_number:
                return HttpResponseBadRequest("Missing 'po_number' in request data.")

            # Create or update the PoNumber entry for the projectName
            obj, created = PoNumber.objects.update_or_create(
                projectName=project_name,
                defaults={"po_number": po_number},
            )

            return JsonResponse({
                "success": True,
                "projectName": obj.projectName,
                "po_number": obj.po_number,
            })

        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON.")
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    else:
        return JsonResponse({"error": "Only POST method allowed."}, status=405)



@csrf_exempt
@require_GET
def get_ponumber(request):
    data = list(PoNumber.objects.values("projectName","po_number"))
    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
def delete_project_folder(request):
    """
    POST JSON:
    {
        "project_name": "702-1-05180 - MFG",
        "dest_path": "Projects"
    }
    """

    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Use POST"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
        project_name = data.get("project_name")
        dest_path = data.get("dest_path", "").strip("/")
        site_url = data.get("site_url", DEFAULT_SP_SITE)

        if not project_name:
            return JsonResponse({"status": "error", "error": "project_name required"}, status=400)

        token = get_access_token()
        site_id = get_site_id(token, site_url)

        if dest_path:
            full_path = f"{dest_path}/{project_name}"
        else:
            full_path = project_name

        safe_path = quote(full_path, safe="/")
        delete_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_path}:"

        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.delete(delete_url, headers=headers)

        if resp.status_code in (200, 204):
            DashboardData.objects.filter(projectName=project_name).delete()
            ProjectData.objects.filter(project_name=project_name).delete()
            OrderStatus.objects.filter(projectName=project_name).delete()
            PoNumber.objects.filter(projectName=project_name).delete()

            return JsonResponse({"status": "ok", "message": f"Deleted {full_path} and DB records"})

        return JsonResponse({
            "status": "error",
            "url_used": delete_url,
            "error": resp.text
        }, status=500)

    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def update_order_status(request):

    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Use POST"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    project_name = data.get("projectName")

    if not project_name:
        return JsonResponse(
            {"error": "projectName is required"},
            status=400,
        )

    # Check if record exists or create new
    try:
        order = OrderStatus.objects.get(projectName=project_name)
        is_new = False
    except OrderStatus.DoesNotExist:
        order = OrderStatus(projectName=project_name)
        order.order_serial = generate_order_serial()
        is_new = True

    # Partial update: update only valid model fields
    model_fields = {f.name for f in order._meta.get_fields()}

    for field, value in data.items():
        if field in model_fields:
            setattr(order, field, value)

    order.save()

    return JsonResponse(
        {
            "message": "Created new record" if is_new else "Updated successfully",
            "order_serial": order.order_serial,
        }
    )


@csrf_exempt
@require_GET
def get_order_status(request):
    data = list(OrderStatus.objects.values("projectName","quotationname","order_serial","po_number","dc_number","dispatch_date","tracking_number","invoice_number","po_status","invoice_status","payment_status", "po_contact"))
    return JsonResponse({"status": "ok", "data": data})

@csrf_exempt
@require_GET
def get_job_data(request):
    data = list(OrderStatus.objects.values("projectName","po_number"))
    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
@require_GET
def fetch_bom_data(request):
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
            "quantity": r.quantity,
            "part_status":r.part_status,
            "part_remark":r.part_remark
        }
        for r in query
    ]


    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
@require_GET
def fetch_order_serial(request):
    data=list(OrderStatus.objects.values("projectName","order_serial"))
    return JsonResponse({"status":"ok","data":data})

@csrf_exempt
@require_GET
def fetch_order_postatus(request):
    data=list(OrderStatus.objects.values("projectName","po_status"))
    return JsonResponse({"status":"ok","data":data})


@csrf_exempt
def update_quotation_name(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Please use POST method"},
            status=400
        )

    key = request.POST.get('projectName')
    new_quote = request.POST.get('quotationname')

    if not key:
        return JsonResponse(
            {"status": "error", "message": "Please provide a valid project name"},
            status=400
        )

    try:
        obj = DashboardData.objects.get(projectName=key)
    except DashboardData.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Project not found"},
            status=404
        )

    obj.quotationname = new_quote
    obj.save()

    return JsonResponse({"status": "success"})

@csrf_exempt
def update_quotation_name(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Please use POST method"},
            status=400
        )

    data = json.loads(request.body)

    key = data.get("projectName")
    new_quote = data.get("quotationname")  # matches payload

    if not key:
        return JsonResponse(
            {"status": "error", "message": "Please provide a valid project name"},
            status=400
        )

    if not new_quote:
        return JsonResponse(
            {"status": "error", "message": "Please make Quotation first"},
            status=400
        )

    updated = DashboardData.objects.filter(
        projectName=key
    ).update(quotationname=new_quote)

    if updated == 0:
        return JsonResponse(
            {"status": "error", "message": "Project not found"},
            status=404
        )

    return JsonResponse({"status": "success"})


@csrf_exempt
def add_on_info(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Please use POST method"}, status=400
        )
    data = json.loads(request.body)

    key = data.get("projectName")
    ext_message = data.get("ext_info")

    if not key:
        return JsonResponse({"Status": "Please provide a valid project name"}, status=400)

    updated = DashboardData.objects.filter(projectName=key).update(ext_info=ext_message)

    return JsonResponse({"Status": "Success"})


@csrf_exempt
def add_pendingpo(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Please use POST method"}, status=400
        )
    data = json.loads(request.body)

    key = data.get("projectName")
    projectStatus = data.get("projectStatus")

    if not key:
        return JsonResponse({"Status": "Please provide a valid project name"}, status=400)

    updated = DashboardData.objects.filter(projectName=key).update(projectStatus=projectStatus)

    return JsonResponse({"Status": "Success"})


#@csrf_exempt
#def add_po_contact(request):
#    if request.method != "POST":
#       return JsonResponse(
#            {"status": "error", "message": "Please use POST method"}, status=400
#        )
#    data = json.loads(request.body)

#    key = data.get("projectName")
#    quotationname = data.get("quotationname")
#    po_number = data.get("po_number")
#    po_contact = data.get("po_contact")

#    if not key:
#        return JsonResponse({"Status": "Please provide a valid project name"}, status=400)

#    updated = OrderStatus.objects.filter(projectName=key).update(quotationname=quotationname, po_contact=po_contact, po_number=po_number)
#
#    if updated == 0:
#        return JsonResponse(
#            {"status": "error", "message": "Project not found"},
#            status=404
#        )
#
#    return JsonResponse({"status": "success"})


@csrf_exempt
def add_po_contact(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Please use POST method"},
            status=400
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON"},
            status=400
        )

    project_name = data.get("projectName")
    if not project_name:
        return JsonResponse(
            {"status": "error", "message": "projectName is required"},
            status=400
        )

    # Try to fetch existing record or create a new instance
    try:
        order = OrderStatus.objects.get(projectName=project_name)
        is_new = False
    except OrderStatus.DoesNotExist:
        order = OrderStatus(projectName=project_name)
        order.order_serial = generate_order_serial()
        is_new = True

    # Only allow real model fields (exclude relations)
    model_fields = {f.name for f in order._meta.fields}

    # Protect fields that must never be overwritten
    protected_fields = {"id", "pk", "projectName"}

    # Partial update: update only provided fields
    for field, value in data.items():
        if field in model_fields and field not in protected_fields:
            setattr(order, field, value)

    order.save()

    return JsonResponse(
        {
            "status": "success",
            "action": "created" if is_new else "updated",
        }
    )


# @csrf_exempt
# def format_file(request):
#     if request.method != "POST":
#         return HttpResponse("Send a PDF file using POST")
   
#     pdf_file = request.FILES.get("pdf")

#     if not pdf_file:
#         return HttpResponse("No PDF uploaded", status=400)

#     fs = FileSystemStorage()

#     input_name = fs.save(pdf_file.name, pdf_file)
#     input_path = fs.path(input_name)

#     output_name = f"edited_{pdf_file.name}"
#     output_path = fs.path(output_name)

#     whiteout_pdf(input_path, output_path)

#     response = FileResponse(
#     open(output_path, "rb"),
#     as_attachment=True,
#     filename=output_name,
#     content_type="application/pdf",
#     )

#     return response


# @csrf_exempt
# def format_file(request):
#     if request.method != "POST":
#         return HttpResponse("Send a ZIP file using POST", status=405)

#     uploaded_zip = request.FILES.get("zip")
#     assembly_client = request.POST.get("assembly_client")

#     if not uploaded_zip:
#         return HttpResponse("No ZIP uploaded", status=400)

#     storage = FileSystemStorage()
#     zip_name = storage.save(uploaded_zip.name, uploaded_zip)
#     zip_path = storage.path(zip_name)

#     output_zip_name = f"{uploaded_zip.name}"
#     output_zip_path = storage.path(output_zip_name)

#     with tempfile.TemporaryDirectory() as extract_dir, tempfile.TemporaryDirectory() as processed_dir:
#         with zipfile.ZipFile(zip_path, "r") as zip_ref:
#             zip_ref.extractall(extract_dir)

#         for root, _, files in os.walk(extract_dir):
#             for file_name in files:
#                 source_path = os.path.join(root, file_name)
#                 relative_path = os.path.relpath(source_path, extract_dir)
#                 destination_path = os.path.join(processed_dir, relative_path)

#                 os.makedirs(os.path.dirname(destination_path), exist_ok=True)

#                 if file_name.lower().endswith(".pdf"):
#                     match assembly_client.lower():
#                         case "vvdn":
#                             vvdn_pdf(source_path, destination_path)
#                         case "asm":
#                             asm_pdf(source_path, destination_path)
#                         case "sanmina":
#                             sanmina_pdf(source_path, destination_path)
#                         case "anora":
#                             anora_pdf(source_path, destination_path)
#                 else:
#                     shutil.copy2(source_path, destination_path)

#         with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
#             for root, _, files in os.walk(processed_dir):
#                 for file_name in files:
#                     file_path = os.path.join(root, file_name)
#                     archive_name = os.path.relpath(file_path, processed_dir)
#                     zip_ref.write(file_path, archive_name)

#     return FileResponse(
#         open(output_zip_path, "rb"),
#         as_attachment=True,
#         filename=output_zip_name,
#         content_type="application/zip",
#     )


@csrf_exempt
def format_file(request):
    if request.method != "POST":
        return HttpResponse("Send a ZIP file using POST", status=405)

    uploaded_zip = request.FILES.get("zip")
    assembly_client = request.POST.get("assembly_client")
    custom_filename = request.POST.get("filename")

    if not uploaded_zip:
        return HttpResponse("No ZIP uploaded", status=400)

    if not custom_filename:
        custom_filename = "download"

    storage = FileSystemStorage()

    zip_name = storage.save(uploaded_zip.name, uploaded_zip)
    zip_path = storage.path(zip_name)

    output_zip_name = f"{custom_filename}.zip"
    output_zip_path = storage.path(output_zip_name)

    with tempfile.TemporaryDirectory() as extract_dir, tempfile.TemporaryDirectory() as processed_dir:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        merged_pdf = fitz.open()

        for root, _, files in os.walk(extract_dir):
            files.sort()

            for file_name in files:
                source_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(source_path, extract_dir)

                original_destination = os.path.join(processed_dir, relative_path)
                os.makedirs(os.path.dirname(original_destination), exist_ok=True)

                # Copy non-PDF files directly
                if not file_name.lower().endswith(".pdf"):
                    shutil.copy2(source_path, original_destination)
                    continue

                temp_pdf_path = os.path.join(
                    processed_dir,
                    f"processed_{file_name}",
                )

                match assembly_client.lower():
                    case "vvdn":
                        vvdn_pdf(source_path, temp_pdf_path)
                    case "asm":
                        asm_pdf(source_path, temp_pdf_path)
                    case "sanmina":
                        sanmina_pdf(source_path, temp_pdf_path)
                    case "anora":
                        anora_pdf(source_path, temp_pdf_path)
                    case _:
                        shutil.copy2(source_path, temp_pdf_path)

                # Save processed PDF in place of original
                shutil.copy2(temp_pdf_path, original_destination)

                # Add processed version to merged PDF
                processed_pdf = fitz.open(temp_pdf_path)
                merged_pdf.insert_pdf(processed_pdf)
                processed_pdf.close()

                os.remove(temp_pdf_path)

        merged_pdf_path = os.path.join(processed_dir, f"{custom_filename}.pdf")
        merged_pdf.save(merged_pdf_path)
        merged_pdf.close()

        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
            for root, _, files in os.walk(processed_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    archive_name = os.path.relpath(file_path, processed_dir)
                    zip_ref.write(file_path, archive_name)

    return FileResponse(
        open(output_zip_path, "rb"),
        as_attachment=True,
        filename=output_zip_name,
        content_type="application/zip",
    )