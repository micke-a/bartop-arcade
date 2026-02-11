# Bartop Arcade Build

Notes about what I end up doing and buying while working through this project.
Mainly notes for myself, but if others find it hopefully it will answer some questions and be helpful. 

## Table of Contents

- [Links](#links)
- [Cabinet](#cabinet)
  - [Cabinet Vinyl](#cabinet-vinyl)
  - [Bezel vinyl](#bezel-vinyl)
  - [How to apply](#how-to-apply)
- [Acrylic sheets for screen cover and marquee](#acrylic-sheets-for-screen-cover-and-marquee)
- [Buttons](#buttons)
- [Marquee back lighting](#marquee-back-lighting)
- [Raspberry Pi](#raspberry-pi)
  - [Software Install](#software-install)
- [Monitor](#monitor)
- [Speakers](#speakers)

## Links

https://www.instructables.com/2-Player-Bartop-Arcade-Machine-Powered-by-Pi/

https://retropie.org.uk/forum/topic/18939/yet-another-arcade-bartop-do-it-yourself-guide-to-build-your-very-own-cabinet-with-raspberry-pi-and-retropie

https://www.tinyarcademachines.com/free-arcade-cabinet-diy-guide/

## Cabinet
Simple option of buying ready cut flatpack kit from eBay.
Bought from the seller [ell-s](https://www.ebay.co.uk/sch/i.html?item=156682869223&rt=nc&_ssn=ell-s) which sells a decently priced build with good reviews.
![flagpack cabinet](images/cabinet-1.png)

### Cabinet Vinyl
Cost £77

Reached out to and double-checked sizing with Rockstar print/arcade first regarding the cabinet sizing and got this reply.

```
Yes those sizes will be fine to order.
I will need the sizes for each of the panels either the 5 set or the 8 so max heights and widths for each please
```

Rockstar is the vinly provider that the ebay seller recommended

Bought the [Sega Nintendo Full Set](https://www.rockstarprint.co.uk/full-set-bartop-.html)

![wrap2](images/SEGANINTENDOFULLSET.jpg)

![Wrap1](images/vinyl-1.png)

### Bezel vinyl
Cost £21 (of which £7 is shipping)

Ordered this from RockStar Print as well, https://www.rockstarprint.co.uk/bezel.html .

What is available by default are all square in dimension, but the above page says to email Sales@rockstarprint.co.uk for custom measures.

My bezel dimensions, given the monitor panel is 540 mm wide and 310 mm high 

- width: 570 mm
- height: 385 mm 
- top/bottom border: 15 mm
- right/left border: 38.5 mm



### How to apply

RockStar were super helpful via email providing advice, and they also include an a4 sheet of paper with instructions.
I watched many youtube videos where people were using the wet method for wood/mdf, but this is not recommended.

* Wood - no water
* Acryclic - wet method recommended (water + a few drops of washing liquids)

Now that I've done it, if you are two people (for the big pieces), putting the vinyl on is pretty easy.


## Acrylic sheets for screen cover and marquee
Cost £24

Ordered from https://www.plasticsheets.com/perspex-sheet-acrylic-sheets/ according to sizes in from the ebay listing.
This place allows you to specify the exact dimensions you want.

* Screen: 570 x 385 x 2mm - £10.54
* Marquee: 570 x 117 x 2mm - £3.20
* shipping £9.95,
* Total cost £23.69

## Buttons
Cost £46

After having looked around all over the place and reading up on sticks and buttons, decided to start simple and
simply bought "EG STARTS 2 Player Arcade Buttons Arcade Contest DIY Retropie Cabinet Kit PC Game + LED Chrome Plating Arcade Buttons Mame Raspberry Pi Game Project" from Amazon

![bottons](images/buttons-1.jpg)

## Marquee back lighting
Cost £9

Had some old left over COB LED strips from when I changed them in the kitchen; this is what I plan to try and use https://www.amazon.co.uk/dp/B0BVR755VK?th=1 .
If ordering a new one I'd probably go for the more bright white option.

What I'm missing is a 12V DC power adapter, got one of these https://www.amazon.co.uk/dp/B019RO949C which works fine.

## Raspberry Pi
Cost ? had one laying about

Have an old PI 4B at home, will start with this one.

### Software Install

First I tried the raspberry pi manager (https://www.raspberrypi.com/software/), but recently they stopped providing the RetroPie as an image option.

So instead I downloaded the image from here https://retropie.org.uk/download/ .

Then used the raspberry pi manager to install the RetroPie image on an SD card.

Plugged the pi into a monitor and it started up just fine.


## Monitor

Cost £79

Cabinet accepts flat screen monitor Size, up to 56.4cm wide x 35.5cm high
(i.e. most 24" widescreen)

Bought this one https://www.scan.co.uk/products/238-aoc-24b3ca2-monitor-ips-1920-x-1080-1ms-adaptivesync-100hz-20m1-250cd-m-hdmi-usb-c

Dimensions without stand: 542.4 x 316.2 x 44.6 (WxHxD)

TODO: notes about settings to automatically power on, does it support what is needed?

## Speakers

Starting with the monitor's built-in speakers, will see later if we upgrade.
