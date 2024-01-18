from LabJackPython import Close, LabJackException
import u3
import numpy as np
import pickle
from time import sleep
#import app


def retry(times, exceptions):
    """
    Retry Decorator
    Retries the wrapped function/method `times` times if the exceptions listed
    in ``exceptions`` are thrown
    :param times: The number of times to repeat the wrapped function/method
    :type times: Int
    :param Exceptions: Lists of exceptions that trigger a retry attempt
    :type Exceptions: Tuple of Exceptions
    """
    def decorator(func):
        def newfn(*args, **kwargs):
            attempt = 0
            while attempt < times:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    print(
                        'Exception thrown when attempting to run %s, attempt '
                        '%d of %d' % (func, attempt, times)
                    )
                    attempt += 1
            return func(*args, **kwargs)
        return newfn
    return decorator

"""
@retry(times=3, exceptions=(ValueError, TypeError))
def foo1():
    print('Some code here ....')
    print('Oh no, we have exception')
    raise ValueError('Some error')

foo1()
"""


"""
how do i initiate and keep track of experiments/processes?
https://www.dataquest.io/blog/python-subprocess/
https://stackoverflow.com/questions/28025402/how-to-kill-subprocesses-when-parent-exits-in-python 

Do i need a pickle for each or is it kept running? probably
"""



def key_for_value(my_dict:dict, value):
    return list(my_dict.keys())[list(my_dict.values()).index(value)]



def valid_sn():
    devices = u3.openAllU3()
    sn = list(devices.keys())
    Close()
    return sn


def kelvin_to_celcius(k):
    return k-273.15

def configure_device(serialNumber, DAC_voltages, ports):
    d = u3.U3(firstFound = False, serial = serialNumber)
    #set all flexible IOs to analog input
    fio = sum([2**x for x in ports if x <= 7])
    eio = sum([2**x for x in ports if x >= 8])
    d.configU3(FIOAnalog = fio, EIOAnalog= eio)
    if DAC_voltages:
        for x,v in enumerate(DAC_voltages):
            d.getFeedback(u3.DAC8(Dac = x, Value = d.voltageToDACBits(v, x )))
    Close()
    return d

def connected_device(serialNumber):
    return u3.U3(firstFound = False, serial = serialNumber)
    
def single_measurement(serialNumber, ports:list = [1,2,3,4,5,6,7,8]): 
    try:
        d = connected_device(serialNumber= serialNumber)
    except Exception as e:
        print("LabJack connection problem", e)
    #ports is as on the assembled instrument 1-16, but the labjack refers to 0-15 
    command_list = [u3.AIN(PositiveChannel=int(x)-1, NegativeChannel=31, LongSettling=True, QuickSample=False) for x in ports]
    bits = d.getFeedback(command_list)
    voltages = d.binaryListToCalibratedAnalogVoltages(bits, isLowVoltage= True, isSingleEnded= True, isSpecialSetting= False )
    Close()
    return voltages

@retry(6,(LabJackException))
def n_measurements(serialNumber, ports:list = [1,2,3,4,5,6,7,8], n_reps = 3):
    return np.array([single_measurement(serialNumber=serialNumber, ports = ports,) for x in range(n_reps) if sleep(1/n_reps) is None]) 

def average_measurement(array = n_measurements):
    return np.ndarray.tolist(np.mean(array, axis = 0))

def stdev_measurement(array = n_measurements):
    return np.std(array, axis = 0)

def get_temp(serialNumber):
   d = connected_device(serialNumber)
   temp = kelvin_to_celcius(d.getTemperature())
   Close()
   return temp

def add_to_file(file_name, list):
    out_file = open(file_name, "a+") #a+ mode creates non-existing file and appends to end if it does exist.
    out_file.write('\t'.join(list) + '\n')
    out_file.close()

CURRENT_RUNS_PICKLE = "Current_runs.pickle"
USAGE_STATUS_PICKLE ="Usage_status.pickle"
PORTS_PER_DEVICE = 16
VALID_SERIAL_NUMBERS = valid_sn()

def make_usage_status_pickle(file = USAGE_STATUS_PICKLE):
    usage_status = {x:[0 for y in range(PORTS_PER_DEVICE)] for x in VALID_SERIAL_NUMBERS}
    with open(file, "wb") as f:
        pickle.dump(usage_status, f, pickle.DEFAULT_PROTOCOL)

def make_current_runs_pickle(file = CURRENT_RUNS_PICKLE):
    with open(file, "wb") as f:
        pickle.dump({}, f, pickle.DEFAULT_PROTOCOL)

def get_usage_status(file = USAGE_STATUS_PICKLE):
    """
    Usage status:
    0 means unused
    1 means in use
    2 means reference in use
    """
    try: 
        with open(file, "rb") as f:
            usage_status = pickle.load(f)
            updated = {device:usage_status[device] for device in VALID_SERIAL_NUMBERS}
            return updated #pickle may contain old devices no longer connected. This obviates those.
    except:
        #usage_status is a dict where Keys:values are serialnumber:list with a 0 for each port.
        make_usage_status_pickle(file = USAGE_STATUS_PICKLE)        
        with open(file, "rb") as f:
            return pickle.load(f)       


def set_usage_status(file = USAGE_STATUS_PICKLE, sn= '320106158', ports_list = [1,2,3,4,5], status = 0):
    """
    Status meaning
    0: unused
    1: used
    2: reference
    """

    usage_status = get_usage_status(file)
    try :
        for port in ports_list:
            usage_status[sn][int(port)-1] = status
    except KeyError:
        if sn in VALID_SERIAL_NUMBERS:
            usage_status[sn] = [0 for y in range(PORTS_PER_DEVICE)]
            for port in ports_list:
                usage_status[sn][int(port)-1] = status 
        else:
            raise KeyError("set_usage_status tried updating an invalid device serial number")
    with open(file, "wb") as f:
        pickle.dump(usage_status, f, pickle.DEFAULT_PROTOCOL)
    return usage_status

def get_unused_ports():
    usage_status = get_usage_status()
    unused_ports = {}
    for device in usage_status.keys():
        unused_ports[device] = [index+1 for index, port in enumerate(usage_status[device]) if port == 0]
    return unused_ports

def flatten_list(input = "listoflists"):
    return [x for xs in input for x in xs]

def get_new_ports(n_ports = 5):
    unused_ports = get_unused_ports()
#    ports_left = len(flatten_list(unused_ports.values()))
    new_ports = {}
#    if ports_left < n_ports:
#        raise ValueError("Not enough ports available in the attached devices. Please attach another device or choose fewer ports.")
    for device, ports in unused_ports.items():                                  #iterate through devices
        new_ports[device] = ports[:n_ports]                                     #collect as many ports as wanted or as available on device (whichever comes first)
        n_ports = n_ports - len(new_ports[device])                              #how many more ports do we need?
        if n_ports == 0:                                                        #stop if we have enough
            break
    return new_ports


