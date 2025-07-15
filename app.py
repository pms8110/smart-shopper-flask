import os
import re
from collections import OrderedDict
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, Response, abort
from flask_sqlalchemy import SQLAlchemy
from flask_babel import Babel, _
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from flask_migrate import Migrate
from sqlalchemy import or_
from fpdf import FPDF
import io
import qrcode
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import requests
import json

# ----------------- بخش ۱: تعریف اپلیکیشن و تنظیمات -----------------
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key-that-you-should-change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'shopping.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
LANGUAGES = {'en': 'English', 'fa': 'فارسی'}
ENCRYPTION_KEY = b'mZt9qB_9rS7uW3xZ6yC4vA1nF0eG5jH8kLp-2vA5gHk='
cipher_suite = Fernet(ENCRYPTION_KEY)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
GEMINI_API_KEY = "" 

def get_locale():
    if 'language' in session and session['language'] in LANGUAGES:
        return session['language']
    return request.accept_languages.best_match(LANGUAGES.keys())

app.config['BABEL_LOCALE_SELECTOR'] = get_locale

db = SQLAlchemy(app)
migrate = Migrate(app, db)
babel = Babel(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = _('Please log in to access this page.')
login_manager.login_message_category = 'error'

# --- توابع کمکی ---
UNIT_SUGGESTIONS = {
    'شیر': 'بطری', 'نوشابه': 'بطری', 'دوغ': 'بطری', 'آب': 'بطری', 'تخم مرغ': 'شانه', 'ماست': 'سطل', 'پنیر': 'بسته', 'کره': 'بسته', 'نان': 'عدد', 'چیپس': 'بسته', 'برنج': 'کیسه', 'گوشت': 'کیلوگرم', 'مرغ': 'کیلوگرم', 'پیاز': 'کیلوگرم', 'سیب زمینی': 'کیلوگرم', 'فرش': 'تخته', 'کتاب': 'جلد', 'milk': 'bottle', 'soda': 'bottle', 'egg': 'carton', 'eggs': 'carton', 'bread': 'loaf', 'cheese': 'pack', 'rice': 'bag', 'meat': 'kg',
}
CATEGORY_SUGGESTIONS = {
    'لبنیات': ['شیر', 'ماست', 'پنیر', 'کره', 'دوغ', 'خامه'], 'پروتئینی': ['گوشت', 'مرغ', 'ماهی', 'تخم مرغ', 'سوسیس', 'کالباس'], 'میوه و سبزیجات': ['سیب', 'پیاز', 'سیب زمینی', 'گوجه', 'خیار', 'کاهو', 'موز'], 'نوشیدنی': ['نوشابه', 'آب', 'آبمیوه', 'دلستر'], 'خشکبار و تنقلات': ['چیپس', 'پفک', 'آجیل', 'شکلات'], 'شوینده و بهداشتی': ['شامپو', 'صابون', 'مایع ظرفشویی', 'دستمال کاغذی'],
}
def find_category(item_name):
    for category, keywords in CATEGORY_SUGGESTIONS.items():
        for keyword in keywords:
            if keyword in item_name.lower(): return category
    return _('Miscellaneous')
def is_password_strong(password):
    if len(password) < 8: return False, _('Password must be at least 8 characters long.')
    if not re.search(r'[a-z]', password): return False, _('Password must contain at least one lowercase letter.')
    if not re.search(r'[A-Z]', password): return False, _('Password must contain at least one uppercase letter.')
    if not re.search(r'[0-9]', password): return False, _('Password must contain at least one number.')
    return True, ""
def calculate_settlements(balances):
    debtors = {user: data for user, data in balances.items() if data['balance'] < -0.01}
    creditors = {user: data for user, data in balances.items() if data['balance'] > 0.01}
    transactions = []
    sorted_debtors = sorted(debtors.items(), key=lambda item: item[1]['balance'])
    sorted_creditors = sorted(creditors.items(), key=lambda item: item[1]['balance'], reverse=True)
    debtor_idx, creditor_idx = 0, 0
    while debtor_idx < len(sorted_debtors) and creditor_idx < len(sorted_creditors):
        debtor_name, debtor_data = sorted_debtors[debtor_idx]
        creditor_name, creditor_data = sorted_creditors[creditor_idx]
        debt, credit = abs(debtor_data['balance']), creditor_data['balance']
        transfer_amount = min(debt, credit)
        transactions.append({'from': debtor_name, 'from_id': debtor_data['user_id'], 'to': creditor_name, 'to_id': creditor_data['user_id'], 'amount': transfer_amount})
        debtor_data['balance'] += transfer_amount
        creditor_data['balance'] -= transfer_amount
        if abs(debtor_data['balance']) < 0.01: debtor_idx += 1
        if abs(creditor_data['balance']) < 0.01: creditor_idx += 1
    return transactions

# ----------------- بخش ۲: مدل‌های پایگاه داده (بدون تغییر) -----------------
list_user_association = db.Table('list_user_association', db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True), db.Column('shopping_list_id', db.Integer, db.ForeignKey('shopping_lists.id'), primary_key=True))
dang_event_participants = db.Table('dang_event_participants', db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True), db.Column('dang_event_id', db.Integer, db.ForeignKey('dang_events.id'), primary_key=True))
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    card_holder_name = db.Column(db.String(200))
    encrypted_card_number = db.Column(db.String(200))
    theme = db.Column(db.String(50), nullable=False, default='light')
    shopping_lists = db.relationship('ShoppingList', backref='owner', lazy='dynamic', foreign_keys='ShoppingList.user_id', cascade="all, delete-orphan")
    shared_shopping_lists = db.relationship('ShoppingList', secondary=list_user_association, lazy='dynamic', backref=db.backref('shared_with_users', lazy='dynamic'))
    dang_events_owned = db.relationship('DangEvent', backref='owner', lazy='dynamic', foreign_keys='DangEvent.user_id', cascade="all, delete-orphan")
    dang_events_participated = db.relationship('DangEvent', secondary=dang_event_participants, lazy='dynamic', backref=db.backref('participants', lazy='dynamic'))
    favorite_items = db.relationship('FavoriteItem', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def set_card_number(self, card_number):
        if card_number: self.encrypted_card_number = cipher_suite.encrypt(card_number.encode()).decode('utf-8')
        else: self.encrypted_card_number = None
    def get_card_number(self):
        if self.encrypted_card_number:
            try: return cipher_suite.decrypt(self.encrypted_card_number.encode()).decode('utf-8')
            except: return "Error decrypting"
        return None
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))
class ShoppingList(db.Model):
    __tablename__ = 'shopping_lists'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    items = db.relationship('Item', backref='list', lazy=True, cascade="all, delete-orphan")
class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.String(200), nullable=True)
    price = db.Column(db.Float, nullable=True, default=0)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    category = db.Column(db.String(100), nullable=True, default=_('Miscellaneous'))
    list_id = db.Column(db.Integer, db.ForeignKey('shopping_lists.id'), nullable=False)
class FavoriteItem(db.Model):
    __tablename__ = 'favorite_items'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
class DangEvent(db.Model):
    __tablename__ = 'dang_events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expenses = db.relationship('Expense', backref='event', lazy=True, cascade="all, delete-orphan")
class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    payer = db.relationship('User', backref='paid_expenses')
    event_id = db.Column(db.Integer, db.ForeignKey('dang_events.id'), nullable=False)
class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('dang_events.id'), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    payer = db.relationship('User', foreign_keys=[payer_id], backref='settlements_made')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='settlements_received')
    event = db.relationship('DangEvent', backref='payments')

# ----------------- بخش ۳: تزریق توابع به قالب‌ها (بدون تغییر) -----------------
@app.context_processor
def inject_global_vars():
    current_lang = get_locale()
    other_lang_code = 'fa' if current_lang == 'en' else 'en'
    other_lang_name = LANGUAGES[other_lang_code]
    return dict(get_locale=get_locale, other_lang={'code': other_lang_code, 'name': other_lang_name})

# ----------------- بخش ۴: مسیرهای برنامه -----------------
# --- تمام روت‌ها تا قبل از روت AI بدون تغییر هستند ---
@app.route('/change-language/<lang>')
def change_language(lang):
    if lang in LANGUAGES: session['language'] = lang
    return redirect(request.referrer or url_for('index'))
@app.route('/change-theme/<theme_name>')
@login_required
def change_theme(theme_name):
    if theme_name in ['light', 'dark', 'ocean']:
        current_user.theme = theme_name
        db.session.commit()
    return redirect(request.referrer or url_for('index'))
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else: flash(_('Invalid username or password'), 'error')
    return render_template('login.html')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_strong, message = is_password_strong(password)
        if not is_strong:
            flash(message, 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash(_('Username already exists. Please choose a different one.'), 'error')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(_('Congratulations, you are now a registered user! Please log in.'), 'success')
            return redirect(url_for('login'))
    return render_template('register.html')
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.card_holder_name = request.form.get('card_holder_name')
        card_number = request.form.get('card_number')
        current_user.set_card_number(card_number)
        db.session.commit()
        flash(_('Your profile has been updated.'), 'success')
        return redirect(url_for('profile'))
    decrypted_card_number = current_user.get_card_number()
    return render_template('profile.html', user=current_user, card_number=decrypted_card_number)
@app.route('/favorites', methods=['GET', 'POST'])
@login_required
def favorites():
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            exists = FavoriteItem.query.filter_by(content=content, user_id=current_user.id).first()
            if not exists:
                new_fav = FavoriteItem(content=content, user=current_user)
                db.session.add(new_fav)
                db.session.commit()
                flash(_('Item "%(content)s" added to favorites.', content=content), 'success')
        return redirect(url_for('favorites'))
    favs = current_user.favorite_items.order_by(FavoriteItem.content).all()
    shopping_lists = current_user.shopping_lists.order_by(ShoppingList.name).all()
    return render_template('favorites.html', favorites=favs, shopping_lists=shopping_lists)
@app.route('/favorites/delete/<int:fav_id>', methods=['POST'])
@login_required
def delete_favorite(fav_id):
    fav_to_delete = FavoriteItem.query.filter_by(id=fav_id, user_id=current_user.id).first_or_404()
    db.session.delete(fav_to_delete)
    db.session.commit()
    flash(_('Favorite item deleted.'), 'info')
    return redirect(url_for('favorites'))
@app.route('/favorites/add_to_list', methods=['POST'])
@login_required
def add_fav_to_list():
    fav_id = request.form.get('fav_id')
    list_id = request.form.get('list_id')
    fav_item = FavoriteItem.query.filter_by(id=fav_id, user_id=current_user.id).first_or_404()
    shopping_list = ShoppingList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    new_item = Item(content=fav_item.content, category=find_category(fav_item.content), list_id=shopping_list.id)
    db.session.add(new_item)
    db.session.commit()
    flash(_('Item "%(item_name)s" added to list "%(list_name)s".', item_name=fav_item.content, list_name=shopping_list.name), 'success')
    return redirect(url_for('favorites'))
@app.route('/toggle_favorite/<int:item_id>', methods=['POST'])
@login_required
def toggle_favorite(item_id):
    item = Item.query.get_or_404(item_id)
    if item.list.owner != current_user and current_user not in item.list.shared_with_users:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    fav_item = FavoriteItem.query.filter_by(content=item.content, user_id=current_user.id).first()
    is_favorite = False
    if fav_item:
        db.session.delete(fav_item)
        db.session.commit()
        is_favorite = False
    else:
        new_fav = FavoriteItem(content=item.content, user=current_user)
        db.session.add(new_fav)
        db.session.commit()
        is_favorite = True
    return jsonify({'success': True, 'is_favorite': is_favorite})
@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('index'))
    accessible_lists_query = db.session.query(ShoppingList.id).filter(or_(ShoppingList.user_id == current_user.id, ShoppingList.shared_with_users.any(id=current_user.id)))
    accessible_list_ids = [id_tuple[0] for id_tuple in accessible_lists_query.all()]
    results = Item.query.filter(Item.list_id.in_(accessible_list_ids), Item.content.ilike(f'%{query}%')).order_by(Item.list_id).all()
    return render_template('search_results.html', results=results, query=query)
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        list_name = request.form.get('list_name')
        if list_name:
            new_list = ShoppingList(name=list_name, owner=current_user)
            db.session.add(new_list)
            db.session.commit()
        return redirect(url_for('index'))
    owned_lists = current_user.shopping_lists.order_by(ShoppingList.id.desc()).all()
    shared_lists = current_user.shared_shopping_lists.order_by(ShoppingList.id.desc()).all()
    return render_template('index.html', owned_lists=owned_lists, shared_lists=shared_lists)
@app.route('/list/<int:list_id>', methods=['GET', 'POST'])
@login_required
def list_view(list_id):
    current_list = ShoppingList.query.get_or_404(list_id)
    if current_list.owner != current_user and current_user not in current_list.shared_with_users:
        flash(_('You do not have permission to access this list.'), 'error'); return redirect(url_for('index'))
    if request.method == 'POST':
        item_content = request.form.get('item')
        if item_content:
            new_item_category = find_category(item_content)
            new_item = Item(content=item_content, quantity=request.form.get('quantity', 1, type=int), unit=request.form.get('unit', ''), notes=request.form.get('notes', ''), price=request.form.get('price', 0, type=float), category=new_item_category, list_id=current_list.id)
            db.session.add(new_item)
            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                item_html = render_template('_item.html', item=new_item)
                return jsonify({'success': True, 'item_html': item_html, 'category': new_item_category})
        return redirect(url_for('list_view', list_id=list_id))
    grouped_items = OrderedDict()
    sorted_items = sorted(current_list.items, key=lambda x: (x.completed, x.category or 'ת', x.id))
    for item in sorted_items:
        category = item.category or _('Miscellaneous')
        if category not in grouped_items:
            grouped_items[category] = []
        grouped_items[category].append(item)
    total_cost = sum(item.price * item.quantity for item in current_list.items)
    completed_cost = sum(item.price * item.quantity for item in current_list.items if item.completed)
    favorites = current_user.favorite_items.order_by(FavoriteItem.content).all()
    return render_template('list_view.html', current_list=current_list, grouped_items=grouped_items, total_cost=total_cost, completed_cost=completed_cost, favorites=favorites)
@app.route('/toggle_item/<int:item_id>', methods=['POST'])
@login_required
def toggle_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.list.owner != current_user and current_user not in item.list.shared_with_users:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    item.completed = not item.completed
    db.session.commit()
    return jsonify({'success': True, 'completed': item.completed})
@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    item_to_delete = Item.query.get_or_404(item_id)
    if item_to_delete.list.owner != current_user and current_user not in item_to_delete.list.shared_with_users:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    db.session.delete(item_to_delete)
    db.session.commit()
    return jsonify({'success': True})
@app.route('/list/<int:list_id>/clear')
@login_required
def clear_list(list_id):
    current_list = ShoppingList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    Item.query.filter_by(list_id=current_list.id).delete()
    db.session.commit()
    flash(_('All items have been cleared from the list "%(list_name)s".', list_name=current_list.name), 'success')
    return redirect(url_for('list_view', list_id=list_id))
@app.route('/delete_list/<int:list_id>')
@login_required
def delete_list(list_id):
    list_to_delete = ShoppingList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    db.session.delete(list_to_delete)
    db.session.commit()
    return redirect(url_for('index'))
@app.route('/update_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def update_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.list.owner != current_user and current_user not in item.list.shared_with_users:
        if request.method == 'GET': return jsonify({'success': False, 'error': 'Permission denied'}), 403
        return redirect(url_for('index'))
    if request.method == 'POST':
        item.content = request.form.get('content', item.content)
        item.quantity = request.form.get('quantity', item.quantity, type=int)
        item.unit = request.form.get('unit', item.unit)
        item.notes = request.form.get('notes', item.notes)
        item.price = request.form.get('price', item.price, type=float)
        item.category = find_category(item.content)
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            item_html = render_template('_item.html', item=item)
            return jsonify({'success': True, 'item_html': item_html, 'category': item.category})
        flash(_('Item updated successfully.'), 'success')
        return redirect(url_for('list_view', list_id=item.list_id))
    return jsonify({'id': item.id, 'content': item.content, 'quantity': item.quantity, 'unit': item.unit, 'notes': item.notes, 'price': item.price})
@app.route('/list/<int:list_id>/share', methods=['GET', 'POST'])
@login_required
def share_list(list_id):
    current_list = ShoppingList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        user_to_share_with = User.query.filter_by(username=request.form.get('username')).first()
        if not user_to_share_with: flash(_('User not found.'), 'error')
        elif user_to_share_with == current_user: flash(_("You can't share a list with yourself."), 'error')
        elif user_to_share_with in current_list.shared_with_users: flash(_('This list is already shared with this user.'), 'error')
        else:
            current_list.shared_with_users.append(user_to_share_with)
            db.session.commit()
            flash(_('List shared successfully with %(username)s.', username=user_to_share_with.username), 'success')
        return redirect(url_for('share_list', list_id=list_id))
    return render_template('share_list.html', current_list=current_list)
@app.route('/list/<int:list_id>/unshare/<int:user_id>')
@login_required
def unshare_list(list_id, user_id):
    current_list = ShoppingList.query.filter_by(id=list_id, user_id=current_user.id).first_or_404()
    user_to_unshare = User.query.get_or_404(user_id)
    if user_to_unshare in current_list.shared_with_users:
        current_list.shared_with_users.remove(user_to_unshare)
        db.session.commit()
        flash(_('Sharing with %(username)s has been revoked.', username=user_to_unshare.username), 'success')
    return redirect(url_for('share_list', list_id=list_id))
@app.route('/dang', methods=['GET', 'POST'])
@login_required
def dang_index():
    if request.method == 'POST':
        event_name = request.form.get('event_name')
        if event_name:
            new_event = DangEvent(name=event_name, owner=current_user)
            new_event.participants.append(current_user)
            db.session.add(new_event)
            db.session.commit()
        return redirect(url_for('dang_index'))
    owned_events = current_user.dang_events_owned.order_by(DangEvent.id.desc()).all()
    participated_events = current_user.dang_events_participated.order_by(DangEvent.id.desc()).all()
    all_events = sorted(list(set(owned_events + participated_events)), key=lambda x: x.id, reverse=True)
    return render_template('dang_index.html', all_events=all_events)
@app.route('/dang/<int:event_id>')
@login_required
def dang_event_view(event_id):
    current_event = DangEvent.query.get_or_404(event_id)
    if current_user not in current_event.participants:
        flash(_('You are not a participant of this event.'), 'error'); return redirect(url_for('dang_index'))
    total_expense = sum(exp.amount for exp in current_event.expenses)
    num_participants = len(current_event.participants.all())
    per_person_share = total_expense / num_participants if num_participants > 0 else 0
    balances = {}
    for user in current_event.participants:
        total_paid_in_expenses = sum(exp.amount for exp in user.paid_expenses if exp.event_id == event_id)
        total_paid_in_settlements = sum(p.amount for p in Payment.query.filter_by(event_id=event_id, payer_id=user.id, is_approved=True).all())
        balance = total_paid_in_expenses + total_paid_in_settlements - per_person_share
        balances[user.username] = {'paid': total_paid_in_expenses + total_paid_in_settlements, 'share': per_person_share, 'balance': balance, 'user_id': user.id}
    proposed_settlements = calculate_settlements(dict(balances))
    active_payments = Payment.query.filter_by(event_id=event_id).all()
    filtered_settlements = []
    for prop in proposed_settlements:
        is_active = False
        for p in active_payments:
            if p.payer_id == prop['from_id'] and p.recipient_id == prop['to_id']:
                is_active = True
                break
        if not is_active:
            filtered_settlements.append(prop)
    is_owner = (current_event.owner == current_user)
    pending_payments = Payment.query.filter_by(event_id=event_id, is_approved=False).all()
    approved_payments = Payment.query.filter_by(event_id=event_id, is_approved=True).all()
    return render_template('dang_event_view.html', current_event=current_event, balances=balances, total_expense=total_expense, is_owner=is_owner, pending_payments=pending_payments, approved_payments=approved_payments, settlements=filtered_settlements)
@app.route('/dang/<int:event_id>/add_expense', methods=['POST'])
@login_required
def add_expense(event_id):
    current_event = DangEvent.query.get_or_404(event_id)
    if current_user not in current_event.participants: return "Unauthorized", 403
    description = request.form.get('description')
    amount = request.form.get('amount', 0, type=float)
    if description and amount > 0:
        new_expense = Expense(description=description, amount=amount, payer=current_user, event_id=current_event.id)
        db.session.add(new_expense)
        db.session.commit()
    return redirect(url_for('dang_event_view', event_id=event_id))
@app.route('/dang/<int:event_id>/manage_participants', methods=['GET', 'POST'])
@login_required
def manage_dang_participants(event_id):
    current_event = DangEvent.query.filter_by(id=event_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        if user and user not in current_event.participants:
            current_event.participants.append(user)
            db.session.commit()
            flash(_('User %(username)s added successfully.', username=user.username), 'success')
        else:
            flash(_('User not found or already in the event.'), 'error')
        return redirect(url_for('manage_dang_participants', event_id=event_id))
    return render_template('manage_dang_participants.html', current_event=current_event)
@app.route('/dang/delete_expense/<int:expense_id>')
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.event.owner != current_user and expense.payer != current_user: return "Unauthorized", 403
    event_id = expense.event_id
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('dang_event_view', event_id=event_id))
@app.route('/dang/delete_event/<int:event_id>')
@login_required
def delete_dang_event(event_id):
    event_to_delete = DangEvent.query.filter_by(id=event_id, user_id=current_user.id).first_or_404()
    db.session.delete(event_to_delete)
    db.session.commit()
    flash(_('Event "%(name)s" has been deleted.', name=event_to_delete.name), 'success')
    return redirect(url_for('dang_index'))
@app.route('/dang/confirm_payment/<int:payment_id>', methods=['POST'])
@login_required
def confirm_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.recipient_id != current_user.id:
        return "Unauthorized", 403
    payment.is_approved = True
    db.session.commit()
    flash(_('Payment from %(user)s has been confirmed.', user=payment.payer.username), 'success')
    return redirect(url_for('dang_event_view', event_id=payment.event_id))
@app.route('/dang/reject_payment/<int:payment_id>', methods=['POST'])
@login_required
def reject_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.recipient_id != current_user.id and payment.event.owner != current_user:
        return "Unauthorized", 403
    event_id = payment.event_id
    db.session.delete(payment)
    db.session.commit()
    flash(_('Payment from %(user)s has been rejected.', user=payment.payer.username), 'error')
    return redirect(url_for('dang_event_view', event_id=event_id))
@app.route('/dang/<int:event_id>/export/<report_format>')
@login_required
def export_dang_report(event_id, report_format):
    current_event = DangEvent.query.get_or_404(event_id)
    if current_user not in current_event.participants:
        flash(_('You are not a participant of this event.'), 'error'); return redirect(url_for('dang_index'))
    total_expense = sum(exp.amount for exp in current_event.expenses)
    num_participants = len(current_event.participants.all())
    per_person_share = total_expense / num_participants if num_participants > 0 else 0
    balances = {}
    for user in current_event.participants:
        total_paid_in_expenses = sum(exp.amount for exp in user.paid_expenses if exp.event_id == event_id)
        total_paid_in_settlements = sum(p.amount for p in Payment.query.filter_by(event_id=event_id, payer_id=user.id, is_approved=True).all())
        total_paid = total_paid_in_expenses + total_paid_in_settlements
        balance = total_paid - per_person_share
        balances[user.username] = {'paid': total_paid, 'share': per_person_share, 'balance': balance, 'user_id': user.id}
    if report_format == 'txt':
        report_content = f"Report for Event: {current_event.name}\n"
        report_content += "=" * 30 + "\n\n"
        report_content += "Participants:\n" + ", ".join([p.username for p in current_event.participants]) + "\n\n"
        report_content += f"Total Expense: {total_expense:,.0f}\n"
        report_content += f"Share per Person: {per_person_share:,.0f}\n\n"
        report_content += "--- Balances ---\n"
        for username, data in balances.items():
            report_content += f"- {username}: Paid: {data['paid']:,.0f}, Balance: {data['balance']:,.0f}\n"
        return Response(report_content, mimetype="text/plain", headers={"Content-disposition": f"attachment; filename=dang_report_{event_id}.txt"})
    elif report_format == 'pdf':
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Report for Event: {current_event.name}", ln=True, align='C')
        pdf.ln(10)
        pdf.cell(200, 10, txt=f"Total Expense: {total_expense:,.0f}", ln=True)
        pdf.cell(200, 10, txt=f"Share per Person: {per_person_share:,.0f}", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="--- Balances ---", ln=True)
        pdf.set_font("Arial", size=12)
        for username, data in balances.items():
            pdf.cell(200, 8, txt=f"- {username}: Paid: {data['paid']:,.0f}, Balance: {data['balance']:,.0f}", ln=True)
        pdf_bytes = pdf.output(dest='S')
        return Response(pdf_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename=dang_report_{event_id}.pdf'})
    return redirect(url_for('dang_event_view', event_id=event_id))
@app.route('/dang/declare_payment', methods=['POST'])
@login_required
def declare_payment_new():
    event_id = request.form.get('event_id')
    payer_id = request.form.get('payer_id')
    recipient_id = request.form.get('recipient_id')
    amount = request.form.get('amount', 0, type=float)
    if current_user.id != int(payer_id):
        return "Unauthorized", 403
    existing_payment = Payment.query.filter_by(event_id=event_id, payer_id=payer_id, recipient_id=recipient_id, is_approved=False).first()
    if existing_payment:
        flash(_('This payment has already been declared and is awaiting confirmation.'), 'info')
    elif amount > 0:
        new_payment = Payment(amount=amount, payer_id=payer_id, recipient_id=recipient_id, event_id=event_id, is_approved=False)
        db.session.add(new_payment)
        db.session.commit()
        flash(_('Your payment has been declared and is awaiting approval.'), 'success')
    return redirect(url_for('dang_event_view', event_id=event_id))
@app.route('/generate_qr/<share_type>/<int:obj_id>')
@login_required
def generate_qr(share_type, obj_id):
    if share_type == 'list':
        obj = ShoppingList.query.filter_by(id=obj_id, user_id=current_user.id).first_or_404()
    elif share_type == 'dang':
        obj = DangEvent.query.filter_by(id=obj_id, user_id=current_user.id).first_or_404()
    else: abort(404)
    token = serializer.dumps({'type': share_type, 'id': obj_id}, salt='share-qr-code')
    join_url = url_for('join_via_link', token=token, _external=True)
    qr_img = qrcode.make(join_url)
    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)
    return Response(img_io, mimetype='image/png')
@app.route('/join/<token>')
@login_required
def join_via_link(token):
    try:
        data = serializer.loads(token, salt='share-qr-code', max_age=3600)
        share_type = data['type']
        obj_id = data['id']
        if share_type == 'list':
            obj = ShoppingList.query.get_or_404(obj_id)
            if current_user in obj.shared_with_users or current_user == obj.owner:
                flash(_('You are already a member of this list.'), 'info')
            else:
                obj.shared_with_users.append(current_user)
                db.session.commit()
                flash(_('You have successfully joined the list "%(name)s"!', name=obj.name), 'success')
            return redirect(url_for('list_view', list_id=obj_id))
        elif share_type == 'dang':
            obj = DangEvent.query.get_or_404(obj_id)
            if current_user in obj.participants:
                flash(_('You are already a participant of this event.'), 'info')
            else:
                obj.participants.append(current_user)
                db.session.commit()
                flash(_('You have successfully joined the event "%(name)s"!', name=obj.name), 'success')
            return redirect(url_for('dang_event_view', event_id=obj_id))
    except SignatureExpired:
        flash(_('The invitation link has expired.'), 'error')
    except BadTimeSignature:
        flash(_('The invitation link is invalid.'), 'error')
    return redirect(url_for('index'))

# ==================================================================
# <<< تغییر جدید: روت ساخت لیست با هوش مصنوعی (با API رایگان داخلی) >>>
# ==================================================================
@app.route('/api/generate-ai-list', methods=['POST'])
@login_required
def api_generate_ai_list():
    user_prompt = request.json.get('prompt')
    if not user_prompt:
        return jsonify({'success': False, 'error': 'No prompt provided.'}), 400

    system_prompt = _("You are a helpful shopping list assistant. Based on the user's request: '%(prompt)s', generate a shopping list. Return the response as a single JSON object with a single key 'items' which contains an array of strings. For example, for 'pancakes', return {\"items\": [\"Flour\", \"Eggs\", \"Milk\", \"Sugar\"]}. Only return the JSON object.", prompt=user_prompt)
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": system_prompt}]}]}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        
        response_json = response.json()
        text_content = response_json['candidates'][0]['content']['parts'][0]['text']
        
        match = re.search(r'\{.*\}', text_content, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in the AI response.")
        
        items_data = json.loads(match.group())
        items_list = items_data.get("items", [])

        if not isinstance(items_list, list):
            raise ValueError("AI did not return a list in the 'items' key.")

        new_list_name = _("AI List: %(prompt)s", prompt=user_prompt)
        new_list = ShoppingList(name=new_list_name, owner=current_user)
        db.session.add(new_list)
        db.session.flush()

        for item_name in items_list:
            if isinstance(item_name, str) and item_name.strip():
                new_item = Item(content=item_name.strip(), category=find_category(item_name), list_id=new_list.id)
                db.session.add(new_item)
        
        db.session.commit()
        return jsonify({'success': True, 'redirect_url': url_for('list_view', list_id=new_list.id)})

    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': f"Could not connect to the AI service: {e}"}), 500
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
        return jsonify({'success': False, 'error': f"The AI returned an unexpected response: {e}"}), 500


# ----------------- بخش ۵: اجرای برنامه -----------------
if __name__ == '__main__':
    app.run(debug=True)
