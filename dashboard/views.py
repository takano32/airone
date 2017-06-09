from airone.lib.http import render


def index(request):
    return render(request, 'dashboard_user_top.html')
