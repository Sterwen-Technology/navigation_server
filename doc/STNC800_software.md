# STNC800 Software

This document explains how to flash or re-flash a STNC800 system and initialize it.

## STNC800 File system

The STNC800 has four possible mass storage devices:

| Type      | device            | partitions     | usage                      |
|-----------|-------------------|----------------|----------------------------|
| SD card   | /dev/mmcblk1      | /dev/mmcblk1p1 | Uboot                      |
|           |                   | /dev/mmcblk1p2 | rootfs / when booting from |
| eMMC      | /dev/mmcblk2boot0 | N/A            | Bootloader                 |
|           | /dev/mmcblk2boot1 | N/A            |                            |    
|           | /dev/mmcblk2      | /dev/mmcblk2p1 | Uboot                      |
|           |                   | /dev/mmcblk2p2 | rootfs (/)                 |
| M.2 SSD   | /dev/nvme0n1      | /dev/nvme0n1p1 | /data                      |
| USB stick | /dev/sda          | /dev/sda1      | /mnt/usb                   |

In normal operation, the eMMC is used for booting and the M.2 SSD is used for storing data.

## Retrieving the firmware

The firmware is available from the [Sterwen-Technology website](https://sterwen-technology.eu/softwares/).

Files to be downloaded:
- Debian base image: to be used a as bootable SD card
- STNC800 firmware: to be flashed on the eMMC
- STNC bootloader firmware: to be flashed on the eMMC


## Preparing the firmware for flash or reflashing

### Flashing a bootable SD card

A bootable SD card is required, and it can be created by flashing the 'imx8mp-sdhc-debian-440bb39.img' file on a SD card.
This can be done on Linux or Windows, preferably with [Etcher](https://www.balena.io/etcher/).

### Copying the full firmware on a USB stick

It is simpler to have the 2 files that have to be flashed on the eMMC on a USB stick, so copy the files:
- stnc-base-V2-2.7.0.img
- u-boot-mmc:2:1-440bb39.bin

## Flashing the firmware

### preparation steps

- insert the SD card in the SD slot
- insert the USB stick in the USB slot
- Connect a console to the serial port of the STNC800 (USB-C to USB-A cable): 115200 8N1

### Boot on the SD card

- power on the STNC800 or perform a power cycle
- Interrupt the boot process by pressing any key on the console when Uboot displays 'Hit any key to stop autoboot'
- When the console shows the U-boot prompt, type
- 'run bootcmd_mmc1'

The system shall boot on the SD card.
login/password is root/root

### Flash the firmware on eMMC

After log on the system, mount the USB stick:
```shell
mkdir /mnt/usb
mount /dev/sda1 /mnt/usb
ls /mnt/usb
```
The Two files to be flashed are:
- stnc-base-V2-2.7.0.img
- u-boot-mmc_2_1-440bb39.bin

Copy the firmware on the eMMC using dd:
```shell
dd if=/mnt/usb/stnc-base-V2-2.7.0.img of=/dev/mmcblk2 bs=4M
```

Copy the bootloader
```shell
# Unlock boot0 
echo 0 > /sys/block/mmcblk2boot0/force_ro 
# Flash flash.bin / u-boot-mmc:2:1-440bb39.bin 
dd if=u-boot-mmc_2_1-440bb39.bin of=/dev/mmcblk2boot0 conv=sync 
# Sync 
sync 
# lock boot0 
echo 1 > /sys/block/mmcblk2boot0/force_ro 
```

### Expending the eMMC partition so it takes the whole available space
```shell
# enter fdisk 
fdisk /dev/mmcblk2 
# delete the last partition (partition 2)
d 
# create a new partition skipping the first one
n 
# select primary partition 
p
# First sector of the new partition
323584
# Last sector of the new partition (take default so all the space is used)
- 
# accept the default 
# print the new table 
p 
# write the new table 
w

# now you need to resize the filesystem 
resize2fs /dev/mmcblk2p2

# sync the changes 
sync
```
**At that stage the system is ready to boot on the eMMC**

## Start from eMMC

- power-off the system
- remove the SD card
- power-on the system

The system shall boot on eMMC. login/password is sterwen/belleile

The STNC software shall be operational, but only the navigation_agent is running all other services are not configured.

Here is the basic configuration:
- navigation_agent is running with no secure communication
- secure communication disabled on all services
- Cellular communication is disabled
- GPS configuration is enabled, but the GNSS service is not started
- M.2 storage is assumed to be present and mounted on /data
- hostname is set to stnc800a00n, better is to change it immediately
- SSH is enabled

Configuration files are located in /home/sterwen/system/conf. They shall be edited and verified before starting the services, although the default configuration is enough for a first test.
