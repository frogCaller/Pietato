# Cameras

Add a camera on the Camera tab or the web page by typing its address. It can be:

- any camera on your network: a webcam a script shares from another computer, an IP camera, an
  ESP32-CAM. Its address and port (like `192.168.1.20:5656`) is enough: the picture is found on its
  page. A link straight to its stream or picture works too.
- a Pi with a USB camera or a camera module: run `sudo bash setup.sh --camera` on it. If the camera turns (an
  OBSBOT, a PTZ webcam), the d-pad steers it.
- a camera plugged into another of your Pietatos: nothing to set up. While it's plugged in, it shows up
  on your other Pietatos' Camera tab under On your network, by that Pietato's name. Only your Pietatos can
  see it, and Settings > Share with other Pietatos turns that off.

A Raspberry Pi camera module (any of Raspberry Pi's, on the Pi's ribbon connector) works like a USB camera. Plug
it in with the Pi off: it's found as the Pi starts. Its picture is made into JPEGs on the Pi while you watch, so it
uses a little more of the Pi than a USB camera does. It can't be steered.

Pis running the camera server show up by themselves under On your network. If a camera is on its
side, press Y on it in your list of cameras to rotate its picture. If it turns the wrong way when you
steer it, press START on it there for its settings: Flip left and right, and Flip up and down.
