from services.sheets_client import sheets_service

def run_test():
    try:
        print("Подключаемся к Google Таблицам...")
        trainers = sheets_service.get_all_trainers()
        print(f"Успех! Найдено тренеров: {len(trainers)}")
        for trainer in trainers:
            print(trainer)
    except Exception as e:
        print(f"Ошибка подключения: {e}")

if __name__ == "__main__":
    run_test()