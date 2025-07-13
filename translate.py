import polib
from googletrans import Translator

# مسیر فایل .po که می‌خواهیم ترجمه کنیم
pofile_path = 'translations/fa/LC_MESSAGES/messages.po'

# بارگذاری فایل .po با استفاده از کتابخانه polib
pofile = polib.pofile(pofile_path)

# ساخت یک نمونه از کلاس مترجم
translator = Translator()

print("شروع فرآیند ترجمه...")

# حلقه زدن روی تمام ورودی‌های فایل که هنوز ترجمه نشده‌اند
for entry in pofile.untranslated_entries():
    # متن اصلی (انگلیسی) را برمی‌داریم
    source_text = entry.msgid
    
    try:
        # متن را به فارسی ترجمه می‌کنیم
        translation = translator.translate(source_text, src='en', dest='fa')
        
        # متن ترجمه شده را در ورودی مربوطه قرار می‌دهیم
        entry.msgstr = translation.text
        
        print(f'"{source_text}"  --->  "{translation.text}"')
    except Exception as e:
        print(f"خطا در ترجمه عبارت: {source_text}. خطا: {e}")

# فایل .po را با تغییرات جدید ذخیره می‌کنیم
pofile.save()

print("ترجمه با موفقیت تمام شد و فایل ذخیره گردید.")