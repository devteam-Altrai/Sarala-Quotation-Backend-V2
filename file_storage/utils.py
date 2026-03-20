import datetime
from .models import OrderStatus


def get_financial_year_code():
    now = datetime.datetime.now()
    year = now.year

    # FY starts in April (04)
    if now.month < 4:  # January–March
        start_year = year - 1
    else:
        start_year = year

    end_year = start_year + 1

    return f"{str(start_year)[-2:]}{str(end_year)[-2:]}"  # "2526"


def generate_order_serial():
    fy_code = get_financial_year_code()  # ex: "2526"
    prefix = "SE-OR-"

    last_entry = (
        OrderStatus.objects.filter(order_serial__contains=f"-{fy_code}-")
        .order_by("-id")
        .first()
    )

    if not last_entry:
        new_number = 1
    else:
        last_serial = last_entry.order_serial.split("-")[-1]
        new_number = int(last_serial) + 1

    return f"{prefix}{fy_code}-{str(new_number).zfill(3)}"
