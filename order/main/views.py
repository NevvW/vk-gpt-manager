from django.shortcuts import render
from django.shortcuts import get_object_or_404, redirect
from .models import Bot
from .forms import BotForm

# Create your views here.
def index(request):
    if not request.user.is_authenticated:
        return redirect("login")

    bot = get_object_or_404(Bot, pk=1)
    if request.method == "POST":
        form = BotForm(request.POST)
        if form.is_valid():
            bot.interval_first = form.cleaned_data['interval_first']
            bot.interval_second = form.cleaned_data['interval_second']
            bot.key_word = form.cleaned_data['key_word']
            bot.text_two_remember = form.cleaned_data['text_two_remember']
            bot.text_one_remember = form.cleaned_data['text_one_remember']
            bot.ban_word = form.cleaned_data['ban_word']
            bot.promt = form.cleaned_data['promt']
            bot.agent_promt = form.cleaned_data['agent_promt']

            bot.proxy_host = form.cleaned_data['proxy_host']
            bot.proxy_port = form.cleaned_data['proxy_port']
            bot.proxy_user = form.cleaned_data['proxy_user']
            bot.proxy_password = form.cleaned_data['proxy_password']

            bot.save()
            return render(request, "index.html", {'form': form})
    else:
        form = BotForm(initial={
            "interval_first": bot.interval_first,
            "interval_second": bot.interval_second,
            "key_word": bot.key_word,
            "ban_word": bot.ban_word,
            "text_two_remember": bot.text_two_remember,
            "text_one_remember": bot.text_one_remember,
            "promt": bot.promt,
            "agent_promt": bot.agent_promt,
            "proxy_host": bot.proxy_host,
            "proxy_port": bot.proxy_port,
            "proxy_user": bot.proxy_user,
            "proxy_password": bot.proxy_password
        })
        
        # print(form)
        return render(request, "index.html", {"form": form})