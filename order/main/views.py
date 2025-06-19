import sqlite3

from django.shortcuts import render
from django.shortcuts import get_object_or_404, redirect
from .models import Bot
from .forms import BotForm
import os


import sys
sys.path.append("..")
from products import excel_products_to_csv

# Create your views here.
def index(request):
    if not request.user.is_authenticated:
        return redirect("login")

    bot = get_object_or_404(Bot, pk=1)
    if request.method == "POST":
        form = BotForm(request.POST, request.FILES)
        print(request.FILES)
        print("get request")
        if 'reset' in request.POST:
            print("reset in request")
            conn: sqlite3.Connection = sqlite3.connect("database.sqlt", check_same_thread=False)
            cursor: sqlite3.Cursor = conn.cursor()

            cursor.execute("DELETE FROM blacklist;")
            cursor.execute("DELETE FROM dialog_history;")
            cursor.execute("DELETE FROM reminder_status;")

            conn.commit()
            cursor.close()
            conn.close()
            return render(request, "index.html", {'form': form})

        if form.is_valid():
            print("Валидация прошла успешно")
            bot.interval_first = form.cleaned_data['interval_first']
            bot.interval_second = form.cleaned_data['interval_second']
            bot.key_word = form.cleaned_data['key_word']
            bot.text_two_remember = form.cleaned_data['text_two_remember']
            bot.text_one_remember = form.cleaned_data['text_one_remember']
            bot.ban_word = form.cleaned_data['ban_word']
            #os.remove(bot.promt)
            bot.agent_promt = form.cleaned_data['agent_promt']

            bot.proxy_host = form.cleaned_data['proxy_host']
            bot.proxy_port = form.cleaned_data['proxy_port']
            bot.proxy_user = form.cleaned_data['proxy_user']
            bot.proxy_password = form.cleaned_data['proxy_password']

            uploaded_file = request.FILES.get("promt", None)
            if uploaded_file:
                # Сохраняем файл куда-нибудь во временную папку или media/
                import os
                from django.core.files.storage import default_storage
                from django.utils import timezone
                try:
                    os.remove(bot.promt.path)
                except:
                    print("Не удалось удалить")
                filename = default_storage.save(f"{uploaded_file.name}", uploaded_file)
                file_path = default_storage.path(filename)

                bot.promt = file_path
                bot.last_change = timezone.now()
                print(bot.promt)

                excel_products_to_csv.toCSV(file_path)
            
            bot.save()
            return render(request, "index.html", {'form': form, "change": bot.last_change})
        
    else:
        form = BotForm(initial={
            "interval_first": bot.interval_first,
            "interval_second": bot.interval_second,
            "key_word": bot.key_word,
            "ban_word": bot.ban_word,
            "text_two_remember": bot.text_two_remember,
            "text_one_remember": bot.text_one_remember,
            # "promt": bot.promt,
            "agent_promt": bot.agent_promt,
            "proxy_host": bot.proxy_host,
            "proxy_port": bot.proxy_port,
            "proxy_user": bot.proxy_user,
            "proxy_password": bot.proxy_password
        })
        
        # print(form)
        return render(request, "index.html", {"form": form, "change": bot.last_change})