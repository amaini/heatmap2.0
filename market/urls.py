from django.urls import path
from . import views


urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.index, name='dashboard'),

    # API endpoints
    path('api/sectors/', views.api_sectors, name='api_sectors'),
    path('api/tickers/', views.api_tickers, name='api_tickers'),
    path('api/lots/', views.api_lots, name='api_lots'),
    path('api/search', views.api_search, name='api_search'),
    path('api/quotes', views.api_quotes, name='api_quotes'),
    path('api/market-status', views.api_market_status, name='api_market_status'),
    path('api/config', views.api_config, name='api_config'),
]
