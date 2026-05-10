import os

from flask import Flask, jsonify, render_template, send_from_directory

from config import apply_config
from db import close_db, init_db, table_names
from visits import tracked_template_response


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    apply_config(app, test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    app.teardown_appcontext(close_db)

    from auth import auth_bp
    from captcha import captcha_bp, lookup_answer_for_tests
    from lineups import lineups_bp
    from admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(captcha_bp)
    app.register_blueprint(lineups_bp)
    app.register_blueprint(admin_bp)

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

    @app.get('/api/health')
    def health():
        return jsonify({'ok': True})

    with app.app_context():
        init_db()

    def get_table_names_for_tests():
        with app.app_context():
            return table_names()

    app.get_table_names = get_table_names_for_tests
    def lookup_captcha_answer_for_tests_wrapper(token):
        with app.app_context():
            return lookup_answer_for_tests(token)

    app.lookup_captcha_answer_for_tests = lookup_captcha_answer_for_tests_wrapper
    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=True)



