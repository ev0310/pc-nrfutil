#
# Copyright (c) 2016 Nordic Semiconductor ASA
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#   1. Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
#   2. Redistributions in binary form must reproduce the above copyright notice, this
#   list of conditions and the following disclaimer in the documentation and/or
#   other materials provided with the distribution.
#
#   3. Neither the name of Nordic Semiconductor ASA nor the names of other
#   contributors to this software may be used to endorse or promote products
#   derived from this software without specific prior written permission.
#
#   4. This software must only be used in or with a processor manufactured by Nordic
#   Semiconductor ASA, or in or with a processor manufactured by a third party that
#   is used in combination with a processor manufactured by Nordic Semiconductor.
#
#   5. Any software provided in binary or object form under this license must not be
#   reverse engineered, decompiled, modified and/or disassembled.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""nrfutil command line tool."""
import os
import sys
import click
import time
import logging
import subprocess
sys.path.append(os.getcwd())

from nordicsemi.dfu.dfu import Dfu
from nordicsemi.dfu.dfu_transport import DfuEvent
from nordicsemi.dfu.dfu_transport_ble import DfuTransportBle
from nordicsemi.dfu.dfu_transport_serial import DfuTransportSerial
from nordicsemi.dfu.package import Package
from nordicsemi import version as nrfutil_version
from nordicsemi.dfu.signing import Signing
from nordicsemi.dfu.util import query_func
from pc_ble_driver_py.exceptions import NordicSemiException, NotImplementedException
from pc_ble_driver_py.ble_driver import BLEDriver, Flasher

def display_sec_warning():
    default_key_warning = """
|===============================================================|
|##      ##    ###    ########  ##    ## #### ##    ##  ######  |
|##  ##  ##   ## ##   ##     ## ###   ##  ##  ###   ## ##    ## |
|##  ##  ##  ##   ##  ##     ## ####  ##  ##  ####  ## ##       |
|##  ##  ## ##     ## ########  ## ## ##  ##  ## ## ## ##   ####|
|##  ##  ## ######### ##   ##   ##  ####  ##  ##  #### ##    ## |
|##  ##  ## ##     ## ##    ##  ##   ###  ##  ##   ### ##    ## |
| ###  ###  ##     ## ##     ## ##    ## #### ##    ##  ######  |
|===============================================================|
|The security key you provided is insecure, as it part of a     |
|known set of keys that have been widely distributed. Do NOT use|
|it in your final product or your DFU procedure may be          |
|compromised and at risk of malicious attacks.                  |
|===============================================================|
"""
    click.echo("{}".format(default_key_warning))


def int_as_text_to_int(value):
    try:
        if value[:2].lower() == '0x':
            return int(value[2:], 16)
        elif value[:1] == '0':
            return int(value, 8)
        return int(value, 10)
    except ValueError:
        raise NordicSemiException('%s is not a valid integer' % value)


class BasedIntOrNoneParamType(click.ParamType):
    name = 'Int or None'

    def convert(self, value, param, ctx):
        try:
            if value.lower() == 'none':
                return 'none'
            return int_as_text_to_int(value)
        except NordicSemiException:
            self.fail('%s is not a valid integer' % value, param, ctx)

BASED_INT_OR_NONE = BasedIntOrNoneParamType()


class TextOrNoneParamType(click.ParamType):
    name = 'Text or None'

    def convert(self, value, param, ctx):
        return value

TEXT_OR_NONE = TextOrNoneParamType()


@click.group()
@click.option('--verbose',
              help='Show verbose information.',
              is_flag=True)
def cli(verbose):
    if verbose:
        logging.basicConfig(format='%(message)s', level=logging.INFO)
    else:
        logging.basicConfig(format='%(message)s')


@cli.command()
def version():
    """Display nrfutil version."""
    click.echo("nrfutil version {}".format(nrfutil_version.NRFUTIL_VERSION))

@cli.group(short_help='Generate and display private and public keys.')
#@click.argument('key_file', required=True, type=click.Path())
def keys():
    """
    This set of commands supports creating and displaying a private (signing) key
    as well as displaying the public (verification) key derived from a private key.
    Private keys are stored in PEM format.
    """
    pass


@keys.command(short_help='Generate a private key and store it in a file in PEM format.')
@click.argument('key_file', required=True, type=click.Path())
              
def generate(key_file):
    signer = Signing()
    
    if os.path.exists(key_file):
        if not query_func("File found at %s. Do you want to overwrite the file?" % key_file):
            click.echo('Key generation aborted.')
            return

    signer.gen_key(key_file)
    click.echo("Generated private key and stored it in: %s" % key_file)

@keys.command(short_help='Display the private key that is stored in a file in PEM format or a public key derived from it.')
@click.argument('key_file', required=True, type=click.Path())
@click.option('--key',
              help='(pk|sk) Display the public key (pk) or the private key (sk).',
              type=click.STRING)
@click.option('--format',
              help='(hex|code|pem) Display the key in hexadecimal format (hex), C code (code), or PEM (pem) format.',
              type=click.STRING)

def display(key_file, key, format):
    signer = Signing()

    if not os.path.isfile(key_file):
        raise NordicSemiException("File not found: %s" % key_file)

    default_key = signer.load_key(key_file)
    if default_key:
        display_sec_warning()

    if not key:
        click.echo("You must specify a key with --key (pk|sk).")
        return
    if key != "pk" and key != "sk":
        click.echo("Invalid key type. Valid types are (pk|sk).")
        return

    if not format:
        click.echo("You must specify a format with --format (hex|code|pem).")
        return
    if format != "hex" and format != "code" and format != "pem":
        click.echo("Invalid format. Valid formats are (hex|code|pem).")
        return


    if key == "pk":
        click.echo(signer.get_vk(format))
    elif key == "sk": 
        click.echo("\nWARNING: Security risk! Do not share the private key.\n")
        click.echo(signer.get_sk(format))


@cli.group(short_help='Generate a Device Firmware Update package.')
def pkg():
    """
    This set of commands supports Nordic DFU package generation.
    """
    pass


@pkg.command(short_help='Generate a firmware package for over-the-air firmware updates.')
@click.argument('zipfile',
                required=True,
                type=click.Path())
@click.option('--application',
              help='The application firmware file.',
              type=click.STRING)
@click.option('--application-version',
              help='The application version. Default: 0xFFFFFFFF',
              type=BASED_INT_OR_NONE,
              default=str(Package.DEFAULT_APP_VERSION))
@click.option('--bootloader',
              help='The bootloader firmware file.',
              type=click.STRING)
@click.option('--bootloader-version',
              help='The bootloader version. Default: 0xFFFFFFFF',
              type=BASED_INT_OR_NONE,
              default=str(Package.DEFAULT_BL_VERSION))
@click.option('--hw-version',
              help='The hardware version. Default: 0xFFFFFFFF',
              type=BASED_INT_OR_NONE,
              default=str(Package.DEFAULT_HW_VERSION))
@click.option('--sd-req',
              help='The SoftDevice requirements. A comma-separated list of SoftDevice firmware IDs (1 or more) '
                   'of which one must be present on the target device. Each item on the list must be in hex and prefixed with \"0x\".'
                   '\nExample #1 (s130 2.0.0 and 2.0.1): --sd-req 0x80,0x87. '
                   '\nExample #2 (s132 2.0.0 and 2.0.1): --sd-req 0x81,0x88. Default: 0xFFFE',
              type=TEXT_OR_NONE,
              default=[str(Package.DEFAULT_SD_REQ[0])],
              multiple=True)
@click.option('--softdevice',
              help='The SoftDevice firmware file.',
              type=click.STRING)
@click.option('--key-file',
              help='The private (signing) key in PEM fomat.',
              type=click.Path(exists=True, resolve_path=True, file_okay=True, dir_okay=False))
def generate(zipfile,
           application,
           application_version,
           bootloader,
           bootloader_version,
           hw_version,
           sd_req,
           softdevice,
           key_file):
    """
    Generate a zip package for distribution to apps that support Nordic DFU OTA.
    The application, bootloader, and SoftDevice files are converted to .bin if supplied as .hex files.
    For more information on the generated package, see:
    http://developer.nordicsemi.com/nRF5_SDK/doc/
    """
    zipfile_path = zipfile

    if application_version == 'none':
        application_version = None

    if bootloader_version == 'none':
        bootloader_version = None

    if hw_version == 'none':
        hw_version = None

    sd_req_list = None
    if len(sd_req) > 1:
        click.echo("Please specify SoftDevice requirements as a comma-separated list: --sd-req 0xXXXX,0xYYYY,...")
        return
    else:
        sd_req = sd_req[0]

    if sd_req.lower() == 'none':
        sd_req_list = []
    elif sd_req:
        try:
            # This will parse any string starting with 0x as base 16.
            sd_req_list = sd_req.split(',')
            sd_req_list = map(int_as_text_to_int, sd_req_list)
        except ValueError:
            raise NordicSemiException("Could not parse value for --sd-req. "
                                      "Hex values should be prefixed with 0x.")
    signer = Signing()
    default_key = signer.load_key(key_file)
    if default_key:
        display_sec_warning()

    package = Package(hw_version,
                      application_version,
                      bootloader_version,
                      sd_req_list,
                      application,
                      bootloader,
                      softdevice,
                      key_file)

    package.generate_package(zipfile_path)

    log_message = "Zip created at {0}".format(zipfile_path)
    click.echo(log_message)


global_bar = None
def update_progress(progress=0):
    if global_bar:
        global_bar.update(progress)

@cli.group(short_help='Perform a Device Firmware Update over a BLE or serial transport.')
def dfu():
    """
    This set of commands supports Device Firmware Upgrade procedures over both BLE and serial transports.
    """
    pass


@dfu.command(short_help="Update the firmware on a device over a serial connection.")
@click.option('-pkg', '--package',
              help='Filename of the DFU package.',
              type=click.Path(exists=True, resolve_path=True, file_okay=True, dir_okay=False),
              required=True)
@click.option('-p', '--port',
              help='Serial port COM port to which the device is connected.',
              type=click.STRING,
              required=True)
@click.option('-b', '--baudrate',
              help='Desired baud rate: 38400/96000/115200/230400/250000/460800/921600/1000000. Default: 38400. '
                   'Note: Physical serial ports (for example, COM1) typically do not support baud rates > 115200.',
              type=click.INT,
              default=DfuTransportSerial.DEFAULT_BAUD_RATE)
@click.option('-fc', '--flowcontrol',
              help='Enable flow control. Default: disabled.',
              type=click.BOOL,
              is_flag=True)
def serial(package, port, baudrate, flowcontrol):
    """Perform a Device Firmware Update on a device with a bootloader that supports serial DFU."""
    raise NotImplementedException('Serial transport currently is not supported')


def enumerate_ports():
    descs   = BLEDriver.enum_serial_ports()
    click.echo('Please select connectivity serial port:')
    for i, choice in enumerate(descs):
        click.echo('\t{} : {} - {}'.format(i, choice.port, choice.serial_number))

    index = click.prompt('Enter your choice: ', type=click.IntRange(0, len(descs)))
    return descs[index].port


@dfu.command(short_help="Update the firmware on a device over a BLE connection.")
@click.option('-pkg', '--package',
              help='Filename of the DFU package.',
              type=click.Path(exists=True, resolve_path=True, file_okay=True, dir_okay=False),
              required=True)
@click.option('-p', '--port',
              help='Serial port COM port to which the connectivity IC is connected.',
              type=click.STRING)
@click.option('-n', '--name',
              help='Device name.',
              type=click.STRING)
@click.option('-a', '--address',
              help='Device address.',
              type=click.STRING)
@click.option('-snr', '--jlink_snr',
              help='Jlink serial number.',
              type=click.STRING)
@click.option('-f', '--flash_connectivity',
              help='Flash connectivity firmware automatically. Default: disabled.',
              type=click.BOOL,
              is_flag=True)
def ble(package, port, name, address, jlink_snr, flash_connectivity):
    """Perform a Device Firmware Update on a device with a bootloader that supports BLE DFU."""
    if name is None and address is None:
        name = 'DfuTarg'
        click.echo("No target selected. Default device name: {} is used.".format(name))

    if port is None and jlink_snr is not None:
        click.echo("Please specify also serial port.")
        return

    elif port is None:
        port = enumerate_ports()

    if flash_connectivity:
        flasher = Flasher(serial_port=port, snr = jlink_snr) 
        if flasher.fw_check():
            click.echo("Connectivity already flashed with firmware.")
        else:
            click.echo("Flashing connectivity ")
            flasher.fw_flash()
            click.echo("Connectivity flashed")
        flasher.reset()
        time.sleep(1)

    ble_backend = DfuTransportBle(serial_port=str(port),
                                  target_device_name=str(name),
                                  target_device_addr=str(address))
    ble_backend.register_events_callback(DfuEvent.PROGRESS_EVENT, update_progress)
    dfu = Dfu(zip_file_path = package, dfu_transport = ble_backend)

    with click.progressbar(length=dfu.dfu_get_total_size()) as bar:
        global global_bar
        global_bar = bar
        dfu.dfu_send_images()

    click.echo("Device programmed.")

if __name__ == '__main__':
    cli()
