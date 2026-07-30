import os
import msal
import shutil
import zipfile
import tempfile
import requests
import pandas as pd
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed

from file_storage.file_formatter_utils.anora_utils import anora_pdf
from file_storage.file_formatter_utils.asm_utils import asm_pdf
from file_storage.file_formatter_utils.sanmina_utils import sanmina_pdf
from file_storage.file_formatter_utils.vvdn_utils import vvdn_pdf
from file_storage.connection_manager import ConnectionManager
from asgiref.sync import async_to_sync 

from file_storage.models import ProjectData, DashboardData





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
# Azure / OneDrive Configuration
# -------------------------------

AZ_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZ_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZ_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
DEFAULT_SP_SITE = os.environ.get("SP_SITE_URL")

def file_processing(uploaded_file, site_url, assembly_client, job_id):
    project_name = os.path.splitext(uploaded_file.name)[0]

    dest_path = ("").strip("/")

    try:
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

            #Extract Zip file
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            excel_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith((".xlsx", ".xls")):
                        excel_file = os.path.join(root, file)
                        break
                    if excel_file:
                        break

            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith(".pdf"):
                        pdf_file = os.path.join(root, file)
                        temp_output = pdf_file + ".tmp.pdf"
                                    
                        match assembly_client.lower():
                            case "vvdn":
                                vvdn_pdf(pdf_file, temp_output)
                                os.replace(temp_output, pdf_file)
                            case "asm":
                                asm_pdf(pdf_file, temp_output)
                                os.replace(temp_output, pdf_file)
                            case "sanmina":
                                sanmina_pdf(pdf_file, temp_output)
                                os.replace(temp_output, pdf_file)
                            case "anora":
                                anora_pdf(pdf_file, temp_output)
                                os.replace(temp_output, pdf_file)
                            case _:
                                pass

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

                async_to_sync(ConnectionManager.send)(
                        job_id,
                        {
                            "type": "test",
                            "message": "Excel parsed and db saved"
                        }
                    )

            else :
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

                async_to_sync(ConnectionManager.send)(
                        job_id,
                        {
                            "type": "test",
                            "message": "Excel parsed and db saved"
                        }
                    )


            token = get_access_token()
            site_id = get_site_id(token, site_url)
            full_folder_path = f"{dest_path}/{project_name}" if dest_path else project_name
            safe_folder_path = quote(full_folder_path, safe="/")

            folder_endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{safe_folder_path}:"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            create_folder_resp = requests.put(folder_endpoint, headers=headers, json={"folder": {}})
            if create_folder_resp.status_code not in (200, 201):
                raise Exception(f"Failed to create folder: {create_folder_resp.status_code} {create_folder_resp.text}")

            session = requests.Session()
            session.headers.update({"Authorization": f"Bearer {token}"})

            uploaded_files = []
            async_to_sync(ConnectionManager.send)(
                        job_id,
                        {
                            "type": "test",
                            "message": "File upload to onedrive started"
                        }
                    )

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


            async_to_sync(ConnectionManager.send)(
                        job_id,
                        {
                            "type": "test",
                            "message": "completed"
                        }
                    )
        return


    except Exception as e:
        async_to_sync(ConnectionManager.send)(
                        job_id,
                        {
                            "type": "test",
                            "message": "Error in uploading try again"
                        }
                    )
        return None