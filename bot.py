import asyncio
import os
import aiofiles
import aiohttp
from io import BytesIO
import requests

from aiogram import Bot, Dispatcher, types
from aiogram import F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile

API_TOKEN = '8043129148:AAEr3TqpPjo6W23BcNONdQEwSXgz0nFQCFM'
PASSWORD = '140824140824'

is_sending_images = False

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

PRINTER_UPLOAD_URL = "http://192.168.0.167/server/files/upload"
TEMP_DIR = 'temp'
BASE_URL = 'http://192.168.0.167'

os.makedirs(TEMP_DIR, exist_ok=True)
session = {'state': 'idle'}
keyboard = ReplyKeyboardMarkup(keyboard=[
    [
        KeyboardButton(text="Остановить печать"),
        KeyboardButton(text="Возобновить печать"),
        KeyboardButton(text="Отменить печать"),
    ],
    [
        KeyboardButton(text="Отключить ОС"),
        KeyboardButton(text="Перезагрузить ОС"),
        KeyboardButton(text="Запустить очередь"),
    ],
    [
        KeyboardButton(text="Остановить очередь"),
        KeyboardButton(text="Обновить машину"),
        KeyboardButton(text="GCODE")
    ],
    [
        KeyboardButton(text="Нагреть стол"),
        KeyboardButton(text="Нагреть сопло"),
        KeyboardButton(text="Охладить"),
    ],
    [
        KeyboardButton(text="Скорость движения"),
        KeyboardButton(text="Подача пластика"),
        KeyboardButton(text="Список файлов")
    ],
    [
        KeyboardButton(text="BEEP"),
        KeyboardButton(text="Home"),
        KeyboardButton(text="M300")
    ],
    [
        KeyboardButton(text="Экстренная остановка"),
        KeyboardButton(text="Движение сопла"),
        KeyboardButton(text="Перезагрузка Firmware")
    ],
    [
        KeyboardButton(text="Полная информация о системе"),
        KeyboardButton(text="Настройки движущейся головки"),
    ],
    [
        KeyboardButton(text="Калибровка принтера (G29)"),
        KeyboardButton(text="Настройки машины"),
        KeyboardButton(text="Фото с камеры")
    ],
    [
        KeyboardButton(text="Misc."),
    ]
])

user_authenticated = {}

@dp.message(lambda message: message.text.lower() == "назад")
async def stop_sending_images(message: types.Message):
    global is_sending_images
    is_sending_images = False
    await message.reply("Остановлено.")

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.reply("Введите пароль для доступа к функциональности бота.")


@dp.message(F.text)
async def check_password(message: types.Message):
    global user_authenticated
    if not user_authenticated.get(message.chat.id, False):
        if message.chat.id in user_authenticated and user_authenticated[message.chat.id]:
            await message.reply("Вы уже аутентифицированы.")
            return

        if message.text == PASSWORD:
            user_authenticated[message.chat.id] = True
            await message.reply("Пароль принят! Теперь вы можете использовать бота.", reply_markup=keyboard)
        else:
            await message.reply("Неверный пароль. Попробуйте еще раз.")
    else:
        await handle_button_press(message)

@dp.message(F.document & F.document.file_name.endswith('.gcode'))
async def handle_gcode_file(message: types.Message):
    if not user_authenticated.get(message.chat.id, False):
        await message.reply("Сначала введите пароль для доступа к функциональности бота.")
        return

    document = message.document
    file_id = document.file_id
    file_info = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as response:
            if response.status != 200:
                await message.reply("Ошибка при загрузке файла.")
                return
            file_path = os.path.join(TEMP_DIR, document.file_name)
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(await response.read())

    await send_to_printer(file_path, document.file_name)
    await message.reply("Файл отправлен на 3D-принтер!")


@dp.message(F.document)
async def handle_invalid_file(message: types.Message):
    if not user_authenticated.get(message.chat.id, False):
        await message.reply("Сначала введите пароль для доступа к функциональности бота.")
        return

    await message.reply("Пожалуйста, отправьте .gcode файл.")

async def send_image_camera(chat_id: int):
    image_url = "http://192.168.0.167/webcam/?action=snapshot"
    response = requests.get(image_url)

    if response.status_code == 200:
        image_bytes = BytesIO(response.content)
        image_bytes.seek(0)

        # Используем BufferedInputFile с BytesIO
        photo = BufferedInputFile(image_bytes.getvalue(), filename="snapshot.jpg")
        await bot.send_photo(chat_id=chat_id, photo=photo)
    else:
        print("Не удалось получить изображение. Код ответа:", response.status_code)

@dp.message(F.text)
async def handle_button_press(message: types.Message):
    global is_sending_images
    if is_sending_images:
        await stop_sending_images(message)
    if not user_authenticated.get(message.chat.id, False):
        await message.reply("Сначала введите пароль для доступа к функциональности бота.")
        return

    button_text = message.text
    if button_text in ["Отключить ОС", "Перезагрузить ОС", 'Обновить машину']:
        await bot.send_message(message.chat.id, 'Принтер возвращается в исходное положение, пожалуйста подождите.')
        await send_request("/printer/gcode/script?script=G28")
    if button_text == 'Назад':
        await stop_sending_images(message)
        is_sending_images = False
    await bot.send_message(message.chat.id, 'Ваша команда выполняется.')

    if button_text == "Остановить печать":
        await send_request("/printer/print/pause")
        await message.reply("Печать остановлена.")
    elif button_text == "Фото с камеры":
        await message.reply("Фото с камеры. (FPS 0.2). Для отмены нажмите назад.", Reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Назад")]]))
        is_sending_images = True

        while is_sending_images:
            await send_image_camera(message.chat.id)
            await asyncio.sleep(5)

    elif button_text == "Misc.":
        await message.reply("Fan: Fan (знач) ||| BeePin (знач) ||| McuFan (знач) ||| ProbeEnable (True/False) ||| SFS T0 (True/False)")
    elif button_text.startswith('Fan') or button_text.startswith('McuFan') or button_text.startswith('ProbeEnable') or button_text.startswith('SFS T0') or button_text.startswith('BeePin'):
        if button_text.startswith("Fan"):
            A_converted = int((int(button_text.split(' ')[-1]) * 255) / 100)
            await send_request(f"/printer/gcode/script?script=M106 S{A_converted}")
            await message.reply(f"Установлено значение {button_text.split(' ')[-1]} для параметра Fan")
        elif button_text.startswith("McuFan"):
            await send_request(f"/printer/gcode/script?script=SET_FAN_SPEED FAN=mcu_fan SPEED={int(button_text.split(' ')[-1])/100}")
            await message.reply(f"Установлено значение {button_text.split(' ')[-1]} для параметра McuFan")
        elif button_text.startswith("BeePin"):
            await send_request(f"/printer/gcode/script?script=SET_PIN PIN=BEEPER_pin VALUE={int(button_text.split(' ')[-1])/100}")
            await message.reply(f"Установлено значение {button_text.split(' ')[-1]} для параметра BeePin")
        elif button_text.startswith("ProbeEnable"):
            if button_text.split(' ')[-1] == "True":
                await send_request(f"/printer/gcode/script?script=SET_PIN PIN=probe_enable VALUE=1.00")
                await message.reply(f"Установлено значение {button_text.split(' ')[-1]} для параметра ProbeEnable")
            else:
                await send_request(f"/printer/gcode/script?script=SET_PIN PIN=probe_enable VALUE=0.00")
                await message.reply(f"Установлено значение {button_text.split(' ')[-1]} для параметра ProbeEnable")
        elif button_text.startswith("SFS T0"):
            if button_text.split(' ')[-1] == "True":
                await send_request(f"/printer/gcode/script?script=SET_FILAMENT_SENSOR SENSOR=SFS_T0 ENABLE=1")
            else:
                await send_request(f"/printer/gcode/script?script=SET_FILAMENT_SENSOR SENSOR=SFS_T0 ENABLE=0")
    elif button_text == "Настройки машины":
        await message.reply("Настройки машины: \nVelocity(mm/s)   |||   Square Corner Velocity(mm/s)\nДля изменения         Для изменения\nVel (знач)        SCV (знач)")
        await message.reply("Acceleration(mm/s^2)   |||   Min. Cruise Ratio(.x)\nДля изменения         Для изменения\nAcc (знач)       MCR (знач)")
    elif button_text.startswith('Vel') or button_text.startswith('Acc') or button_text.startswith('MCR') or button_text.startswith('SCV'):
        if button_text == "Vel":
            await send_request(f"/printer/gcode/script?script=SET_VELOCITY_LIMIT VELOCITY={button_text.split(' ')[-1]}")
        elif button_text == "Acc":
            await send_request(f"/printer/gcode/script?script=SET_VELOCITY_LIMIT ACCEL={button_text.split(' ')[-1]}")
        elif button_text == "MCR":
            await send_request(f"/printer/gcode/script?script=SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO={button_text.split(' ')[-1]}")
        elif button_text == "SCV":
            await send_request(f"/printer/gcode/script?script=SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY={button_text.split(' ')[-1]}")
    elif button_text == "Настройки движущейся головки":
        await message.reply("Настройки движущейся головки: ", reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Z-Offset")],
            [
                KeyboardButton(text="+0.005 Z-Off"),
                KeyboardButton(text="+0.01 Z-Off"),
                KeyboardButton(text="+0.025 Z-Off"),
                KeyboardButton(text="+0.05 Z-Off"),
            ],
            [
                KeyboardButton(text="-0.005 Z-Off"),
                KeyboardButton(text="-0.01 Z-Off"),
                KeyboardButton(text="-0.025 Z-Off"),
                KeyboardButton(text="-0.05 Z-Off"),
            ],
            [
                KeyboardButton(text="Сохранить настройки Offset"),
                KeyboardButton(text="Сбросить настройки Offset"),
            ],
            [
                KeyboardButton(text="Назад"),
            ]
        ]))
    elif button_text == "Сохранить настройки Offset":
        await send_request("/printer/gcode/script?script=Z_OFFSET_APPLY_PROBE")
        await message.reply("Настройки сохранены. Машина перезагрузится.")
        await send_request("/printer/gcode/script?script=SAVE_CONFIG")
    elif button_text == "Сбросить настройки Offset":
        await send_request("/printer/gcode/script?script=SET_GCODE_OFFSET Z=0 MOVE=1")
        await message.reply("Настройки сброшены.")
    elif button_text.endswith('Z-Off'):
        parts = button_text.split(' ')
        koeff = parts[0]
        await message.reply(f"Калибровка принтера: {koeff} Z-Offset.")
        await send_request(f"/printer/gcode/script?script=SET_GCODE_OFFSET Z_ADJUST={koeff} MOVE=1")
    elif button_text == "Калибровка принтера (G29)":
        await send_request("/printer/gcode/script?script=G29")
        await message.reply("Калибровка принтера.")
    elif button_text == "Экстренная остановка":
        await send_request("/printer/emergency_stop")
        await message.reply("Экстренная остановка.")
    elif button_text == "Перезагрузка Firmware":
        await send_request("/printer/firmware_restart")
        await message.reply("Перезагрузка Firmware.")
    elif button_text == "Возобновить печать":
        await send_request("/printer/print/resume")
        await message.reply("Печать возобновлена.")
    elif button_text == "Отменить печать":
        await send_request("/printer/print/cancel")
        await message.reply("Печать отменена.")
    elif button_text == "Отключить ОС":
        await send_request("/machine/shutdown")
        await message.reply("ОС отключается.")
    elif button_text == "Перезагрузить ОС":
        await message.reply("ОС перезагружается.")
        await send_request("/machine/reboot")
    elif button_text == "Запустить очередь":
        await send_request("/server/job_queue/start")
        await message.reply("Очередь запущена.")
    elif button_text == "Остановить очередь":
        await send_request("/server/job_queue/pause")
        await message.reply("Очередь остановлена.")
    elif button_text == "Обновить машину":
        await message.reply("Машина обновляется.")
        await send_request("/machine/update/full")
    elif button_text == "Нагреть стол":
        await message.reply("Отправьте желаемую температуру ответом на это сообщение.")
        session['state'] = 'temperature_bed'
    elif button_text == "Нагреть сопло":
        await message.reply("Отправьте желаемую температуру ответом на это сообщение.")
        session['state'] = 'temperature_extruder'
    elif button_text == "Охладить":
        await message.reply("Охлаждаю")
        await send_request(f"/printer/gcode/script?script=TURN_OFF_HEATERS")
    elif session['state'] == 'temperature_extruder':
        await send_request(f"/printer/gcode/script?script=SET_HEATER_TEMPERATURE HEATER=extruder TARGET={message.text}")
        session['state'] = 'idle'
        await message.reply("Сопло нагревается.")
    elif session['state'] == 'temperature_bed':
        await send_request(f"/printer/gcode/script?script=SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={message.text}")
        session['state'] = 'idle'
        await message.reply("Стол нагревается.")
    elif button_text == 'Скорость движения':
        session['state'] = 'extruder_speed'
        await message.reply("Отправьте новую скорость движения сопла ответом на это сообщение.")
    elif session['state'] == 'extruder_speed':
        await send_request(f"/printer/gcode/script?script=M220 S{message.text}")
        session['state'] = 'idle'
        await message.reply("Установлена новая скорость движения сопла.")
    elif button_text == 'Подача пластика':
        session['state'] = 'plastic_speed'
        await message.reply("Отправьте новую скорость подачи пластика ответом на это сообщение.")
    elif session['state'] == 'plastic_speed':
        await send_request(f"/printer/gcode/script?script=M221 S{message.text}")
        session['state'] = 'idle'
        await message.reply("Установлена новая скорость подачи пластика.")
    elif button_text == 'BEEP':
        await send_request(f"/printer/gcode/script?script=BEEP")
        await message.reply("Сигнал подан")
    elif button_text == 'M300':
        await send_request(f"/printer/gcode/script?script=M300")
        await message.reply("Сигнал подан")
    elif button_text == 'Home':
        await send_request(f"/printer/gcode/script?script=G28")
        await message.reply("Возвращение к исходной точке G28")
    elif button_text == 'Список файлов' or button_text.startswith('Нет, выбрать другое.'):
        json1 = await send_get_request(f'/server/files/list')
        print(json1)
        print(type(json1))
        files = json1['result']
        paths = [item["path"] for item in files]
        print(paths)
        newfil = '\n'.join(paths)
        text = f'Доступные файлы для печати: \n {newfil} Для печати напишите Печать (имя файла).'
        await message.reply(str(text))
    elif button_text.startswith('Печать'):
        parts = button_text.split(' ')
        print(parts)
        print(parts[1:])
        parts = ' '.join(parts[1:])
        await send_ask_message(parts, message)
    elif button_text.startswith('Да, начать печать '):
        parts = button_text.split(' ')[-1]
        await bot.send_message(message.chat.id, f'Печать началась.')
        requests.post(f'http://192.168.0.167/printer/print/start?filename={parts}')
    elif button_text.startswith('Движение сопла'):
        await bot.send_message(message.chat.id, f'Выберите желаемые координати движения сопла кнопками ниже. Если вы хотите указать абсолютную позицию сопла: Установить сопло X Y Z', reply_markup=ReplyKeyboardMarkup(keyboard=[
            [
                KeyboardButton(text='-100X'),
                KeyboardButton(text='-10X'),
                KeyboardButton(text='-1X'),
                KeyboardButton(text='X'),
                KeyboardButton(text='+1X'),
                KeyboardButton(text='+10X'),
                KeyboardButton(text='+100X'),
            ],
            [
                KeyboardButton(text='-100Y'),
                KeyboardButton(text='-10Y'),
                KeyboardButton(text='-1Y'),
                KeyboardButton(text='Y'),
                KeyboardButton(text='+1Y'),
                KeyboardButton(text='+10Y'),
                KeyboardButton(text='+100Y'),
            ],
            [
                KeyboardButton(text='-100Z'),
                KeyboardButton(text='-10Z'),
                KeyboardButton(text='-1Z'),
                KeyboardButton(text='Z'),
                KeyboardButton(text='+1Z'),
                KeyboardButton(text='+10Z'),
                KeyboardButton(text='+100Z'),
            ],
            [
                KeyboardButton(text='Назад'),
            ]
        ]))
    elif button_text.startswith('Установить сопло'):
        parts = button_text.split(' ')
        Z = parts[-1]
        Y = parts[-2]
        X = parts[-3]
        requests.post(f'http://192.168.0.167/printer/gcode/script?script=G1 X{X} Y{Y} Z{Z}')
        await bot.send_message(message.chat.id, f'Сопло установлено.')
    elif button_text.endswith('X') or button_text.endswith('Y') or button_text.endswith('Z'):
        parts = button_text.split()
        axis = parts[-1][-1]
        print(axis)
        print(parts)
        print(parts[0][0:-1])
        quantity = ''.join(parts[0][0:-1])
        requests.post(f'http://192.168.0.167/printer/gcode/script?script=G91\nG1 {axis} {quantity}\nG90')
        await bot.send_message(message.chat.id, f'Сопло установлено')
    elif button_text.startswith('Назад'):
        await bot.send_message(message.chat.id, f'Вы вернулись назад.', reply_markup=keyboard)
        is_sending_images = False
    elif button_text.startswith('Состояние принтера'):
        json1 = await send_get_request(f'/printer/info')
        text = f'Состояние принтера: {json1["state"]}\nОтвет принтера: {json1["state_message"]}\nИмя хоста: {json1["hostname"]}\nВерсия машины: {json1["software_version"]}\nПроцессор: {json1["cpu_info"]}\nKlipperPath: {json1["klipper_path"]}\nPythonPath: {json1["python_path"]}\nLogfile: {json1["log_file"]}\nConfigfile: {json1["config_file"]}'
        await message.reply(str(text))
    elif button_text.startswith('Полная информация о системе'):
        json_data = await send_get_request(f'/machine/system_info')
        json_data = json_data["result"]
        if not json_data:
            await bot.send_message(message.chat.id, 'Не удалось получить информацию о системе.')
        else:
            text = "Информация о системе: \n"
            text = ""

            try:
                text += f"Количество процессоров: {json_data['system_info']['cpu_info']['cpu_count']}\n"
            except KeyError:
                pass

            try:
                text += f"Разрядность: {json_data['system_info']['cpu_info']['bits']}\n"
            except KeyError:
                pass

            try:
                text += f"Процессор: {json_data['system_info']['cpu_info']['processor']}\n"
            except KeyError:
                pass

            try:
                text += f"Описание процессора: {json_data['system_info']['cpu_info']['cpu_desc']}\n"
            except KeyError:
                pass

            try:
                text += f"Серийный номер процессора: {json_data['system_info']['cpu_info']['serial_number']}\n"
            except KeyError:
                pass

            try:
                text += f"Описание оборудования: {json_data['system_info']['cpu_info']['hardware_desc']}\n"
            except KeyError:
                pass

            try:
                text += f"Модель: {json_data['system_info']['cpu_info']['model']}\n"
            except KeyError:
                pass

            try:
                text += f"Общий объем памяти: {json_data['system_info']['cpu_info']['total_memory']} {json_data['system_info']['cpu_info']['memory_units']}\n"
            except KeyError:
                pass

            try:
                text += f"Производитель SD-карты: {json_data['system_info']['sd_info']['manufacturer']}\n"
            except KeyError:
                pass

            try:
                text += f"ID производителя SD-карты: {json_data['system_info']['sd_info']['manufacturer_id']}\n"
            except KeyError:
                pass

            try:
                text += f"OEM ID SD-карты: {json_data['system_info']['sd_info']['oem_id']}\n"
            except KeyError:
                pass

            try:
                text += f"Название продукта SD-карты: {json_data['system_info']['sd_info']['product_name']}\n"
            except KeyError:
                pass

            try:
                text += f"Версия продукта SD-карты: {json_data['system_info']['sd_info']['product_revision']}\n"
            except KeyError:
                pass

            try:
                text += f"Серийный номер SD-карты: {json_data['system_info']['sd_info']['serial_number']}\n"
            except KeyError:
                pass

            try:
                text += f"Дата производства SD-карты: {json_data['system_info']['sd_info']['manufacturer_date']}\n"
            except KeyError:
                pass

            try:
                text += f"Емкость SD-карты: {json_data['system_info']['sd_info']['capacity']}\n"
            except KeyError:
                pass

            try:
                text += f"Общее количество байт на SD-карте: {json_data['system_info']['sd_info']['total_bytes']}\n"
            except KeyError:
                pass

            try:
                text += f"Операционная система: {json_data['system_info']['distribution']['name']}\n"
            except KeyError:
                pass

            try:
                text += f"ID ОС: {json_data['system_info']['distribution']['id']}\n"
            except KeyError:
                pass

            try:
                text += f"Версия ОС: {json_data['system_info']['distribution']['version']}\n"
            except KeyError:
                pass

            try:
                text += f"Кодовое имя ОС: {json_data['system_info']['distribution']['codename']}\n"
            except KeyError:
                pass

            try:
                text += f"Доступные сервисы: {', '.join(json_data['system_info']['available_services'])}\n"
            except KeyError:
                pass

            try:
                text += f"ID сервиса Moonraker: {json_data['system_info']['instance_ids']['moonraker']}\n"
            except KeyError:
                pass

            try:
                text += f"ID сервиса Klipper: {json_data['system_info']['instance_ids']['klipper']}\n"
            except KeyError:
                pass

            try:
                text += f"Состояние сервиса Klipper: {json_data['system_info']['service_state']['klipper']['active_state']}, "
                text += f"подсостояние: {json_data['system_info']['service_state']['klipper']['sub_state']}\n"
            except KeyError:
                pass

            try:
                text += f"Состояние сервиса Klipper MCU: {json_data['system_info']['service_state']['klipper_mcu']['active_state']}, "
                text += f"подсостояние: {json_data['system_info']['service_state']['klipper_mcu']['sub_state']}\n"
            except KeyError:
                pass

            try:
                text += f"Состояние сервиса Moonraker: {json_data['system_info']['service_state']['moonraker']['active_state']}, "
                text += f"подсостояние: {json_data['system_info']['service_state']['moonraker']['sub_state']}\n"
            except KeyError:
                pass

            try:
                text += f"Тип виртуализации: {json_data['system_info']['virtualization']['virt_type']}\n"
            except KeyError:
                pass

            try:
                text += f"Идентификатор виртуализации: {json_data['system_info']['virtualization']['virt_identifier']}\n"
            except KeyError:
                pass

            try:
                text += f"Версия Python: {'.'.join(map(str, json_data['system_info']['python']['version'][:3]))}\n"
            except KeyError:
                pass

            try:
                text += f"Строка версии Python: {json_data['system_info']['python']['version_string']}\n"
            except KeyError:
                pass

            try:
                text += f"MAC-адрес WLAN0: {json_data['system_info']['network']['wlan0']['mac_address']}\n"
            except KeyError:
                pass

            try:
                text += f"IP-адреса WLAN0: {', '.join([ip['address'] for ip in json_data['system_info']['network']['wlan0']['ip_addresses']])}\n"
            except KeyError:
                pass

            try:
                text += f"CAN шина 0: Длина очереди передачи: {json_data['system_info']['canbus']['can0']['tx_queue_len']}, "
                text += f"скорость передачи: {json_data['system_info']['canbus']['can0']['bitrate']}, "
                text += f"драйвер: {json_data['system_info']['canbus']['can0']['driver']}\n"
            except KeyError:
                pass

            try:
                text += f"CAN шина 1: Длина очереди передачи: {json_data['system_info']['canbus']['can1']['tx_queue_len']}, "
                text += f"скорость передачи: {json_data['system_info']['canbus']['can1']['bitrate']}, "
                text += f"драйвер: {json_data['system_info']['canbus']['can1']['driver']}\n"
            except KeyError:
                pass
            await bot.send_message(message.chat.id, text)
async def send_ask_message(parts, message):
    print(parts)
    kv = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=f'Да, начать печать {parts}'),
         KeyboardButton(text='Нет, выбрать другое.')]
    ])
    await bot.send_message(message.chat.id, f'----------------------------------------------------\nВы уверены что хотите запустить печать {parts}?', reply_markup=kv)
@dp.message(F.text & F.reply_to_message)
async def handle_gcode_lines(message: types.Message):
    if not user_authenticated.get(message.chat.id, False):
        await message.reply("Сначала введите пароль для доступа к функциональности бота.")
        return
    gcode_lines = message.text.splitlines()
    for line in gcode_lines:
        await send_request(f"/printer/gcode/script?script={line}")
    await message.reply("Строки GCODE отправлены на принтер.")

async def send_to_printer(file_path, name):
    with open(file_path, 'rb') as f:
        files = {'file': f}
        headers = {
            'X-KL-Ajax-Request': 'Ajax_Request',
            'Accept': 'application/json, text/plain, */*',
        }
        response = requests.post(PRINTER_UPLOAD_URL, files=files, headers=headers)

    if response.status_code == 201:
        print(f'http://192.168.0.167/printer/print/start?filename={name}')
        print("Файл успешно отправлен на принтер")
        print(name)
        printresponse = requests.post(f'http://192.168.0.167/printer/print/start?filename={name}')
        print("Ответ от сервера:", response.json())
        print('Ответ принтера:', printresponse.json())
    else:
        print("Ошибка при отправке файла:", response.status_code, response.text)


async def send_request(endpoint):
    response = requests.post(BASE_URL + endpoint)
    if response.status_code == 200:
        print(f"Успешно отправлен запрос на {endpoint}")
    else:
        print(f"Ошибка при отправке запроса на {endpoint}: {response.status_code}, {response.text}")
async def send_get_request(endpoint):
    response = requests.get(BASE_URL + endpoint)
    if response.status_code == 200:
        print(f"Успешно отправлен запрос на {endpoint}")
        return response.json()
    else:
        print(f"Ошибка при отправке запроса на {endpoint}: {response.status_code}, {response.text}")

async def main():
    try:
        print("Бот запущен...")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == '__main__':
    asyncio.run(main())
