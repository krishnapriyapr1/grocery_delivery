from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from . import views
from .payment_views import process_payment
from .auth_views import login_view, logout_view
from .supplier_views import (
    supplier_dashboard,
    supplier_restock_requests,
    update_restock_request
)
from . import stock_views
from . import admin_views
from . import admin_order_views, admin_delivery_views
from .delivery_views import delivery_register
from .chat_views import send_chat_message, get_quick_messages

urlpatterns = [
    # Main URLs
    path('', views.home, name='home'),
    path('products/', views.product_list, name='product_list'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('category/<slug:category_slug>/', views.category_products, name='category_products'),
    path('search/', views.search, name='search'),
    
    # Cart URLs
    path('cart/', views.view_cart, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:item_id>/', views.update_cart, name='update_cart'),
    path('cart/add-ajax/', views.add_to_cart_ajax, name='add_to_cart_ajax'),
    path('cart/update-ajax/<int:item_id>/', views.update_cart_ajax, name='update_cart_ajax'),
    path('cart/remove-ajax/<int:item_id>/', views.remove_from_cart_ajax, name='remove_from_cart_ajax'),
    path('checkout/', views.checkout, name='checkout'),
    
    # Payment URLs
    path('payment/', views.payment_page, name='payment'),
    path('process-payment/', process_payment, name='process_payment'),
    
    # Order URLs
    path('orders/', views.my_orders, name='my_orders'),  
    path('order/history/', views.order_history, name='order_history'),  
    path('order/confirmation/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
    path('order/tracking/<int:order_id>/', views.order_tracking, name='order_tracking'),
    path('order/detail/<int:order_id>/', views.order_detail, name='order_detail'),
    
    # User URLs
    path('profile/', views.profile, name='profile'),
    
    # Admin URLs
    path('store-admin/', views.admin_dashboard, name='admin_dashboard'),
    path('store-admin/categories/', views.admin_categories, name='admin_categories'),
    path('store-admin/categories/<int:category_id>/', views.edit_category, name='edit_category'),
    path('store-admin/categories/<int:category_id>/delete/', views.delete_category, name='delete_category'),
    path('store-admin/products/', views.admin_products, name='admin_products'),
    path('store-admin/products/<int:product_id>/', views.edit_product, name='edit_product'),
    path('store-admin/products/<int:product_id>/delete/', views.delete_product, name='delete_product'),
    path('store-admin/suppliers/', views.admin_suppliers, name='admin_suppliers'),
    path('store-admin/supplier/<int:supplier_id>/', admin_views.supplier_details, name='supplier_details'),
    path('store-admin/supplier/<int:supplier_id>/toggle-status/', admin_views.toggle_supplier_status, name='toggle_supplier_status'),
    path('store-admin/supplier/message/<int:supplier_id>/', views.send_supplier_message, name='send_supplier_message'),
    path('store-admin/stock/', admin_views.stock_management, name='admin_stock_management'),  
    path('store-admin/stock/management/', stock_views.admin_stock, name='stock_management'),  
    path('store-admin/stock/restock-product/<int:product_id>/', admin_views.create_restock_request, name='create_restock_request'),
    path('store-admin/stock/assign-supplier/', stock_views.assign_supplier, name='assign_supplier'),
    path('store-admin/stock/update-reorder-level/<int:product_id>/', stock_views.update_reorder_level, name='update_reorder_level'),
    
    # Admin stock management
    path('store-admin/stock/management/', stock_views.admin_stock, name='admin_stock_management'),
    path('store-admin/stock/restock-product/<int:product_id>/', admin_views.create_restock_request, name='create_restock_request'),
    path('store-admin/stock/assign-supplier/', stock_views.assign_supplier, name='assign_supplier'),
    
    # Order Management URLs
    path('store-admin/orders/', admin_order_views.admin_orders, name='admin_orders'),
    path('store-admin/order/<int:order_id>/', admin_order_views.admin_view_order_details, name='admin_view_order_details'),
    path('store-admin/order/<int:order_id>/update-status/', admin_order_views.update_order_status, name='update_order_status'),
    path('store-admin/order/assign-delivery/', admin_order_views.assign_delivery, name='assign_delivery'),
    
    # Delivery Management URLs
    path('store-admin/delivery/', admin_delivery_views.admin_delivery_management, name='admin_delivery_management'),
    path('store-admin/delivery/boy/<int:delivery_boy_id>/performance/', admin_delivery_views.delivery_boy_performance, name='delivery_boy_performance'),
    path('store-admin/delivery/boy/<int:delivery_boy_id>/<str:action>/', admin_delivery_views.manage_delivery_boy, name='manage_delivery_boy'),
    
    # Sales Report URLs
    path('store-admin/sales-report/', admin_order_views.admin_monthly_sales_report, name='admin_monthly_sales_report'),
    path('store-admin/sales-report/download/', admin_order_views.download_monthly_sales_report, name='download_monthly_sales_report'),
    
    # Admin Message URLs
    path('store-admin/messages/', views.admin_messages, name='admin_messages'),
    
    path('store-admin/product/add/', views.add_product, name='add_product'),
    path('store-admin/product/edit/<int:product_id>/', views.edit_product, name='edit_product'),
    path('store-admin/product/delete/<int:product_id>/', views.delete_product, name='delete_product'),
    path('store-admin/category/add/', views.add_category, name='add_category'),
    path('store-admin/supplier/<int:supplier_id>/toggle/', views.toggle_supplier_approval, name='toggle_supplier_approval'),
    path('store-admin/supplier/message/<int:supplier_id>/', views.send_supplier_message, name='send_supplier_message'),
    
    # Admin product approval URLs
    path('store-admin/product-approvals/', admin_views.manage_product_approvals, name='manage_product_approvals'),
    path('store-admin/product-approvals/<int:product_id>/update/', admin_views.update_product_approval, name='update_product_approval'),
    
    # Supplier URLs
    path('supplier/dashboard/', supplier_dashboard, name='supplier_dashboard'),
    path('supplier/restock-requests/', supplier_restock_requests, name='supplier_restock_requests'),
    path('supplier/restock-request/<int:request_id>/update/', update_restock_request, name='update_restock_request'),
    
    # Delivery URLs - grouped together
    path('delivery/', include([
        path('register/', delivery_register, name='delivery_register'),
        path('login/', views.delivery_login, name='delivery_login'),
        path('dashboard/', views.delivery_dashboard, name='delivery_dashboard'),
        path('orders/', views.delivery_orders, name='delivery_orders'),
        path('toggle-availability/', views.toggle_delivery_availability, name='toggle_delivery_availability'),
        path('update-status/<int:assignment_id>/', views.update_delivery_status, name='update_delivery_status'),
        path('chat/<int:order_id>/', views.delivery_chat, name='delivery_chat'),
    ])),
    
    # Chat URLs
    path('chat/send/', send_chat_message, name='send_chat_message'),
    path('chat/quick-messages/', get_quick_messages, name='get_quick_messages'),
    
    # Authentication URLs
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', views.register, name='register'),
    
    # Supplier URLs
    path('supplier/login/', views.supplier_login, name='supplier_login'),
    path('supplier/register/', views.supplier_register, name='supplier_register'),
    path('supplier/products/', views.supplier_products, name='supplier_products'),
    path('supplier/messages/', views.supplier_messages, name='supplier_messages'),
    path('supplier/product/<int:product_id>/update-stock/', views.update_stock, name='update_stock'),
]
