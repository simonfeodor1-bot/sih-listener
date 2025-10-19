#
# Файл: api/index.py
# Назначение: Наша "Ловушка" (Serverless Function) для Vercel.
#

from flask import Flask, request, jsonify
import psycopg2
import os

# Создаем Flask-приложение
app = Flask(__name__)

# Vercel будет обращаться к этому приложению
# Нам не нужен 'handler', Vercel сам найдет 'app'
@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def catch_all(path):
    
    # Наш URL будет /api/index.py, 
    # но Vercel может направить сюда и другие запросы.
    # Мы хотим отвечать только на наш целевой POST-запрос.
    if request.method != 'POST':
        return jsonify({"status": "error", "message": "Method not allowed"}), 405

    # --- Шаг 0: Получаем "секреты" из Vercel ---
    # Vercel хранит их в os.environ
    # Мы настроим их в Шаге 4
    sih_secret = os.environ.get('SIH_WEBHOOK_SECRET')
    db_url = os.environ.get('POSTGRES_DATABASE_URL')
    
    if not sih_secret or not db_url:
        # Это для логов Vercel
        print("ERROR: SIH_WEBHOOK_SECRET or POSTGRES_DATABASE_URL not set")
        return jsonify({"status": "error", "message": "Server configuration error"}), 500

    # --- Шаг А: Безопасность (Аутентификация) ---
    received_secret = request.headers.get('X-Webhook-Secret')
    
    if received_secret != sih_secret:
        print(f"WARN: Unauthorized access. Invalid X-Webhook-Secret.")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # --- Шаг Б: Извлечение данных ---
    try:
        data = request.json
        item_data = data.get('item', {})
        market_hash_name = item_data.get('market_hash_name')
        deal_price = data.get('dealPrice')
        
        provider_name = data.get('provider')
        suggested_price = data.get('suggestedPrice')

        if not market_hash_name or deal_price is None:
            print("ERROR: Missing 'market_hash_name' or 'dealPrice'")
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
    except Exception as e:
        print(f"ERROR: JSON parsing error: {e}")
        return jsonify({"status": "error", "message": "Bad Request"}), 400

    # --- Шаг В и Г: Подключение к БД и Запись ---
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO sih_provider_prices 
                (market_hash_name, price, provider_platform_name, suggested_steam_price)
            VALUES 
                (%s, %s, %s, %s)
            ON CONFLICT (market_hash_name) 
            DO UPDATE SET
                price = EXCLUDED.price,
                provider_platform_name = EXCLUDED.provider_platform_name,
                suggested_steam_price = EXCLUDED.suggested_steam_price,
                updated_at = CURRENT_TIMESTAMP;
        """, (market_hash_name, deal_price, provider_name, suggested_price))

        conn.commit()
        
        print(f"INFO (Vercel Cloud): Price for '{market_hash_name}' updated: {deal_price} USD")
        return jsonify({"status": "ok", "message": "Webhook received"}), 200

    except (Exception, psycopg2.Error) as e:
        print(f"ERROR: PostgreSQL error: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": "Database error"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
