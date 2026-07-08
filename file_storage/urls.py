from django.urls import path
from . import views

urlpatterns = [

    path('formatfile/', views.format_file, name="format_file"),
    path ("delete/", views.delete_project_folder, name="delete_project_folder"), # This endpoint will be used to delete the folder
    #path("rename_quote/", views.update_quotation_name, name="update_quotation_name"), # This endpoint will update the quotation name.
    # This path's handle the quoatation data which will be displayed dashboard
    path('quote/', views.quote_name, name='quote_name'),   # for saving/updating the single string
    path('get_quote/', views.get_quote, name='get_quote'), # for fetching the stored string
    path('get_metadata/', views.get_dashboard_data, name='get_dashboard_data'),
    path('update_dashboard/',views.update_dashboard, name='update_dashboard'),
    path('add_po/', views.status_detail, name='status_detail'),# This endpoint is used to post the po number
    path('fetch_po/', views.get_ponumber, name='get_ponumber'),# This endpoint is used to get the po number
    path('orderstatus/', views.update_order_status, name='update_order_status'),# This endpoint is used to create or update the order status
    path('getorderstatus/',views.get_order_status , name= 'get_order_status'), # This endpoint is used to get the order status
    path('jobdata/', views.get_job_data, name='get_job_data'),# This endpoint is used to job status
    path("fetchbom/", views.fetch_bom_data, name="fetch_bom_data"), #Fetch the meta data for the every part(by Part no.).
    path("fetchorderserial/", views.fetch_order_serial, name="fetch_order_serial"), #Fetch the orderserial number.
    path("fetchorderpostatus/", views.fetch_order_postatus, name="fetch_order_postatus"), #Fetch the order postatus
    path("rename_quote/", views.update_quotation_name, name="update_quotation_name"), # This endpoint will update the quotation name.
    path("addinfo/", views.add_on_info, name="add_on_info"), # This endpoint saves the info of project on dashboard
    path("addcontact/", views.add_po_contact, name="add_po_contact"),
    path("pending/",views.add_pendingpo, name="add_pendingpo"),

    #The Below paths handles all the file operations
    path("upload/zip/", views.upload_zip, name="upload_zip"), # upload the zip to the Sharepoint.
    path("fetch/", views.fetch_data, name="fetch_data"), #Fetch the meta data for the every part(by Part no.).
    path("update_cost/", views.update_cost, name="update_cost"), # Update the cost of a particular part (by it Part no.).
    path("pricelist/", views.price_list_fetch, name="price_list_fetch"),# The API which fetches the pricelist
    path("list_zip_files/", views.list_zip_files, name="list_zip_files"), # get the list of all the zip/folder file in the onedrive.
    path("<str:project_name>/", views.fetch_all_files, name="fetch_all_files"),#This give the filename and the download url



]