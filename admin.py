# admin.py
from flask import Blueprint, render_template, request, jsonify, send_file, session, redirect, url_for, abort
from models import db, LoginLog, FAQ, User
from datetime import datetime
import csv, io, json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return wrapped

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    total_logins = LoginLog.query.count()
    recent_logs = LoginLog.query.order_by(LoginLog.time.desc()).limit(50).all()
    return render_template('admin_dashboard.html', total_logins=total_logins, recent_logs=recent_logs)

@admin_bp.route('/clear_logs', methods=['POST'])
@admin_required
def clear_logs():
    LoginLog.query.delete()
    db.session.commit()
    return jsonify({'status': 'ok'})

@admin_bp.route('/download_logs')
@admin_required
def download_logs():
    logs = LoginLog.query.order_by(LoginLog.time.desc()).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['time','kind','user','success','ip'])
    for l in logs:
        cw.writerow([l.time.isoformat(), l.kind, l.user, 'Yes' if l.success else 'No', l.ip])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    filename = f'logs_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.csv'
    return send_file(mem, as_attachment=True, download_name=filename, mimetype='text/csv')

@admin_bp.route('/add_faq', methods=['POST'])
@admin_required
def add_faq():
    question = request.form.get('question','').strip()
    answer = request.form.get('answer','').strip()
    if not question or not answer:
        return jsonify({'status':'error','msg':'invalid input'}), 400
    f = FAQ(question=question, answer=answer)
    db.session.add(f)
    db.session.commit()
    return jsonify({'status':'ok','id':f.id})

@admin_bp.route('/export_faqs')
@admin_required
def export_faqs():
    faqs = FAQ.query.order_by(FAQ.created_at.desc()).all()
    out = [{'id':f.id,'question':f.question,'answer':f.answer,'created_at':f.created_at.isoformat()} for f in faqs]
    return jsonify(out)

@admin_bp.route('/import_faqs', methods=['POST'])
@admin_required
def import_faqs():
    # Accept JSON body or file upload
    if request.is_json:
        data = request.get_json()
    else:
        # support file upload form
        file = request.files.get('file')
        if not file:
            return jsonify({'status':'error','msg':'no file'}), 400
        try:
            data = json.load(file)
        except Exception:
            return jsonify({'status':'error','msg':'invalid json'}), 400
    if not isinstance(data, list):
        return jsonify({'status':'error','msg':'expected list'}), 400
    created = 0
    for item in data:
        q = item.get('question','').strip()
        a = item.get('answer','').strip()
        if q and a:
            db.session.add(FAQ(question=q, answer=a))
            created += 1
    db.session.commit()
    return jsonify({'status':'ok','created':created})

@admin_bp.route('/chart_data')
@admin_required
def chart_data():
    # Example aggregation: count of FAQs (or a QuestionLog table) by category.
    # If you have a QuestionLog table, replace with aggregation there.
    # We'll show counts of FAQs for demo, and a static fallback.
    faqs = FAQ.query.count()
    # Example static buckets (replace with real aggregation if you store question topics)
    labels = ['Account Balance','Card Status','Loan Rates','Branch IFSC','Send Money','Support Hours']
    # For demo, sample values (or compute real values via a QuestionLog model)
    values = [42, 34, 28, 22, 18, 12]
    return jsonify({'labels': labels, 'values': values, 'faq_count': faqs})