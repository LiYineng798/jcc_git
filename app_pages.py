import os

from flask import jsonify, send_from_directory

from auth import login_required
from visits import tracked_template_response


def register_page_routes(app):
    @app.get('/')
    def index():
        return tracked_template_response('index.html', 'home')

    @app.get('/auth')
    def auth_page():
        return tracked_template_response('auth.html', 'auth')

    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon',
        )

    @app.get('/lineup/new')
    def lineup_create_page():
        return tracked_template_response('lineup_form.html', 'lineup_editor', lineup_id='', page_mode='create')

    @app.get('/lineup/<int:lineup_id>/edit')
    def lineup_edit_page(lineup_id):
        return tracked_template_response('lineup_form.html', 'lineup_editor', lineup_id=lineup_id, page_mode='edit')

    @app.get('/lineup/<int:lineup_id>')
    def lineup_detail_page(lineup_id):
        return tracked_template_response('lineup_detail.html', 'lineup_detail', lineup_id=lineup_id)

    @app.get('/author/<username>')
    def author_page(username):
        return tracked_template_response('author.html', 'author', username=username)

    @app.get('/tools/lineup-simulator')
    def lineup_simulator_page():
        return tracked_template_response('lineup_simulator.html', 'lineup_simulator')

    @app.get('/me')
    def account_page():
        user, error = login_required()
        if error:
            return error
        return tracked_template_response('account.html', 'account')

    @app.get('/api/health')
    def health():
        return jsonify({'ok': True})


def register_test_helpers(app, get_table_names_func, lookup_captcha_answer_func):
    app.get_table_names = get_table_names_func
    app.lookup_captcha_answer_for_tests = lookup_captcha_answer_func
