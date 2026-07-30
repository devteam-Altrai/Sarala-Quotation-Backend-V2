import os
import fitz
import shutil
import zipfile
import datetime
from .models import OrderStatus
from django.core.files.storage import FileSystemStorage
from file_storage.file_formatter_utils.vvdn_utils import vvdn_pdf
from file_storage.file_formatter_utils.asm_utils import asm_pdf
from file_storage.file_formatter_utils.sanmina_utils import sanmina_pdf
from file_storage.file_formatter_utils.anora_utils import anora_pdf

def get_financial_year_code():
    now = datetime.datetime.now()
    year = now.year

    # FY starts in April (04)
    if now.month < 4:   # January–March
        start_year = year - 1
    else:
        start_year = year

    end_year = start_year + 1

    return f"{str(start_year)[-2:]}{str(end_year)[-2:]}"  # "2526"


def generate_order_serial():
    fy_code = get_financial_year_code()      # ex: "2526"
    prefix = "SE-OR-"

    last_entry = (
        OrderStatus.objects
        .filter(order_serial__contains=f"-{fy_code}-")
        .order_by("-id")
        .first()
    )

    if not last_entry:
        new_number = 1
    else:
        last_serial = last_entry.order_serial.split("-")[-1]
        new_number = int(last_serial) + 1

    return f"{prefix}{fy_code}-{str(new_number).zfill(3)}"


def whiteout_pdf(input_path, output_path):
    doc = fitz.open(input_path)

    for page in doc:
        logo_rect = fitz.Rect(945, 675, 1158, 738)
        page.add_redact_annot(logo_rect, fill=(1, 1, 1))

        vertical_rect = fitz.Rect(1177, 170, 1190, 710)
        page.add_redact_annot(vertical_rect, fill=(1, 1, 1))

       
        description_rect = fitz.Rect(738.5, 658.5, 1160, 670)
        page.add_redact_annot(description_rect, fill=(1, 1, 1))

        page.apply_redactions()

    doc.save(output_path, garbage=4, clean=True)
    doc.close()