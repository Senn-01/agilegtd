from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('process/', views.ProcessInboxView.as_view(), name='process_inbox'),
    path('backlog/', views.BacklogView.as_view(), name='backlog'),
    path('history/', views.HistoryView.as_view(), name='history'),
    path('sprint/', views.SprintView.as_view(), name='sprint'),
    path('retrospective/', views.RetrospectiveView.as_view(), name='retrospective'),
] 