from datetime import datetime


def check_float(potential_float):
    try:
        float(potential_float)
        return True
    except ValueError:
        return False

def convert_time(time_string):
    try:
        return datetime.strptime(time_string, "%H:%M")
    except ValueError:
        return None

def convert_decimal(decimal_string):
    try:
        return float(format(float(decimal_string), '.1f'))
    except ValueError:
        return None