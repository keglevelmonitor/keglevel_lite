## 💻 KegLevel Lite Project
 
**KegLevel Lite** app is a "stripped-down" version of the **KegLevel Monitor** app. It allows homebrewers to monitor and track the level of beer in their kegs. Up to 5 kegs are supported.

Currently tested only on the Raspberry Pi 3B running Trixie and Bookworm. Should work with RPi4 and RPi5 running the same OS's but not yet tested.

## To Install the KegLevel Lite App

Open **Terminal** and run this command. Type carefully and use proper uppercase / lowercase because it matters:

```bash
bash <(curl -sL bit.ly/keglevel)
```

Please **donate $$** if you use the app. See "Support the app" under the Settings & Info menu.


Information on the full **KegLevel Monitor** app can be found here:
**🔗 [KegLevel Monitor Project](https://github.com/keglevelmonitor/keglevelmonitor)** 


There is also a **🔗 [Fermentation Vault Project](https://github.com/keglevelmonitor/fermvault)** project in the repository. The FermVault app monitors the temperature of a fermenting product (beer, wine, mead, etc.) inside a refrigerator or freezer. The app turns the refrigerator/freezer on or off, and optionally a heater on or off, to maintain a consistent fermentation temperature. The temperature of the fermenting product can be used as the control-to point. PID regulation ensures accurate temperature control with very little or no overshoot or undershoot of the setpoint temperature. Robust email notifications allow flexible remote monitoring and remote email control of the FermVault system. 


## To uninstall the KegLevel Lite app

Selections within the uninstall script allow you to:
* uninstall only the app, leaving the settings folder intact (APP)
    this is useful if you wish to reinstall the app but retain settings
    (deletes ~/keglevel_lite contents and all of its subfolders)
    (deletes the desktop shortcut from the Other launch menu)
* uninstall the app and all of its settings (ALL)
    (deletes everything above)
    (deletes ~/keglevel_lite-data contents)
* exit without doing anything

To uninstall, open **Terminal** and run this command. Type carefully and use proper uppercase / lowercase because it matters:

```bash
bash <(curl -sL https://bit.ly/uninstall-keglevel-lite)
```

## ⚙️ For reference
Installed file structure:

```
~/keglevel_lite/
├── all of the app's management files...
│
├── src/
│   ├── all of the app's source code...
│   │
│   └── assets/
│        └── all of the app's asset files...
│
├── venv/
│   └── virtual environment and dependencies...
│            
~/keglevel_lite-data/
    └── all of the app settings json's...
    
System-level dependencies installed via sudo apt outside of venv:
sudo apt-get install -y python3-tk python3-dev swig python3-venv liblgpio-dev
sudo to install all of the kivy dependencies, and there are a lot of them

```


