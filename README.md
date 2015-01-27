# Automatic WeMo light control for XBMC
This addon takes a single WeMo lightswitch or socket and turns it off when playback starts, and turns it back on again when playback stops.

This plugin was tested on XMBC/Kodi running on an Ouya (Android) device, but should be platform-independant. If you run into any issues using this plugin, feel free to [open a bug report on GitHub](https://github.com/MidnightLightning/Kodi-Wemo-controller/issues).

## Install release version
[Download latest](https://github.com/MidnightLightning/Kodi-Wemo-controller/releases) ZIP file, and install [as an XBMC/Kodi addon](http://kodi.wiki/view/HOW-TO:Install_an_Add-on_from_a_zip_file).

## Build from Source
Clone the git repository, and then from within the project directory, run

    make

That will create a `release` folder, and put a `service.wemo.lightswitch.zip` file in it. Install that ZIP as an addon to XBMC/Kodi.

Really, all the release process does is ZIP up the `service.wemo.lightswitch` directory, which you could do with any archive utility (make sure you zip up the folder, and not just the contents of the folder), so if you don't have `make` installed, try that route.

## Contributors

* Brooks Boyd (MidnightLightning)
* Luke Metzinger (Treads6465)