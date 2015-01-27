# Automatic WeMo light control for XBMC
This addon takes a single WeMo lightswitch or socket and turns it off when playback starts, and turns it back on again when playback stops.

This plugin was tested on XMBC/Kodi running on an Ouya (Android) device, but should be platform-independant. If you run into any issues using this plugin, feel free to open a bug report on GitHub.

## Build from Source
Clone the git repository, and then from within the project directory, run

    make

That will create a `release` folder, and put a `service.wemo.lightswitch.zip` file in it. Install that ZIP as an addon to XBMC/Kodi.
