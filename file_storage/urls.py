from django.urls import path
from . import views

urlpatterns = [

    

    # This path's handle the quoatation data which will be displayed dashboard
    path('quote/', views.quote_name, name='quote_name'),   # for saving/updating the single string
    path('get_quote/', views.get_quote, name='get_quote'), # for fetching the stored string
    path('get_metadata/', views.get_dashboard_data, name='get_dashboard_data'),
    path('update_dashboard/',views.update_dashboard, name='update_dashboard'),

    #The Below paths handles all the file operations
    path("upload/zip/", views.upload_zip, name="upload_zip"), # upload the zip to the Sharepoint.
    path("fetch/", views.fetch_data, name="fetch_data"), #Fetch the meta data for the every part(by Part no.).
    path("update_cost/", views.update_cost, name="update_cost"), # Update the cost of a particular part (by it Part no.).
    path("pricelist/", views.price_list_fetch, name="price_list_fetch"),# The API which fetches the pricelist
    path("list_zip_files/", views.list_zip_files, name="list_zip_files"), # get the list of all the zip/folder file in the onedrive. 
    path("<str:project_name>/", views.fetch_all_files, name="fetch_all_files"),#This give the filename and the download url 
    
    
]