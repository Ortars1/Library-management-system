# tests/simple_fuzzing.py — лучший из двух миров
import requests
import random
import string
import time

BASE_URL = "http://localhost:8000"

def random_string(min_len=0, max_len=100):
    length = random.randint(min_len, max_len)
    chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:',.<>?/`~"
    return ''.join(random.choices(chars, k=length))

def random_email():
    if random.random() > 0.5:
        return random_string(1, 10) + "@" + random_string(1, 5) + "." + random_string(2, 3)
    return random_string(1, 30)

def fuzz_register_endpoint(iterations=100):
    print(f"[*] Фаззинг регистрации: {iterations} итераций")
    stats = {"200": 0, "400": 0, "422": 0, "500": 0, "error": 0}
    crashes = []  # ← сохраняем краши
    
    for i in range(iterations):
        test_data = {
            "username": random_string(0, 60),
            "email": random_email(),
            "password": random_string(0, 100)
        }
        try:
            response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=test_data, timeout=5)
            stats[str(response.status_code)] = stats.get(str(response.status_code), 0) + 1
            
            if response.status_code == 500:
                crashes.append({"iteration": i, "data": test_data})
                print(f"  [!] CRASH на итерации {i}: {test_data}")
                
        except Exception as e:
            stats["error"] += 1
            crashes.append({"iteration": i, "error": str(e)})
            
        if (i + 1) % 25 == 0:
            print(f"  [+] Прогресс: {i+1}/{iterations}")
    
    return stats, crashes

def fuzz_book_endpoint(iterations=100):
    print(f"\n[*] Фаззинг создания книги: {iterations} итераций")
    
    login = requests.post(f"{BASE_URL}/api/v1/auth/login", 
                          json={"username": "admin", "password": "admin123"})
    if login.status_code != 200:
        print("  [!] Ошибка: Не получен токен. Запустите сервер.")
        return {"error": True}, []
    
    headers = {"Authorization": f"Bearer {login.json()['access_token']}", "Content-Type": "application/json"}
    stats = {"200": 0, "400": 0, "422": 0, "500": 0, "error": 0}
    crashes = []
    
    for i in range(iterations):
        test_data = {
            "isbn": random_string(5, 20),
            "title": random_string(1, 200),
            "author": random_string(1, 100),
            "year": random.randint(1000, 3000),
            "total_copies": random.randint(-10, 50)
        }
        try:
            response = requests.post(f"{BASE_URL}/api/v1/books", json=test_data, headers=headers, timeout=5)
            stats[str(response.status_code)] = stats.get(str(response.status_code), 0) + 1
            
            if response.status_code == 500:
                crashes.append({"iteration": i, "data": test_data})
                print(f"  [!] CRASH: {test_data}")
                
        except Exception as e:
            stats["error"] += 1
            crashes.append({"iteration": i, "error": str(e)})
            
        if (i + 1) % 25 == 0:
            print(f"  [+] Прогресс: {i+1}/{iterations}")
    
    return stats, crashes

if __name__ == "__main__":
    print("ФАЗЗИНГ-ТЕСТИРОВАНИЕ УСТОЙЧИВОСТИ API")
    print("=" * 60)
    
    start = time.time()
    stats_reg, crashes_reg = fuzz_register_endpoint(100)
    stats_book, crashes_book = fuzz_book_endpoint(100)
    elapsed = time.time() - start
    
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 60)
    print(f"Регистрация: {stats_reg}")
    print(f"Создание книг: {stats_book}")
    
    total_500 = stats_reg.get("500", 0) + stats_book.get("500", 0)
    total_crashes = len(crashes_reg) + len(crashes_book)
    
    print(f"\nОшибок сервера (500): {total_500}")
    print(f"Сохранено крашей: {total_crashes}")
    print(f"Время: {elapsed:.2f} сек")
    
    if total_500 == 0:
        print("\n✅ ВЫВОД: Ошибок 500 не обнаружено.")
    else:
        print(f"\n❌ ВЫВОД: Обнаружено {total_500} ошибок сервера. Требуется анализ.")
        if total_crashes > 0:
            print("   Данные о крашах сохранены для воспроизведения.")