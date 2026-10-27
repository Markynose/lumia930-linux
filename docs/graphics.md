# X11 and GPU bring-up plan

planned work, not a working graphical desktop or GPU-support claim. the tested
kernel has `CONFIG_DRM` disabled, uses `CONFIG_FB_SIMPLE` and inherits firmware
scanout. touchscreen input works in the separate GPIO61 pull-up RAM test.

## first X11 stack

use packaged Alpine armv7 Xorg for the initial bring-up, not a new display
server build. the basic display path is `xf86-video-fbdev` on the existing
framebuffer. this is unaccelerated and does not require a working GPU.

preferred small phone-oriented WM candidate: `sxmo-dwm`, the mobile-patched
X11 dwm fork, plus `svkbd` for the on-screen keyboard. both are present in the
Alpine armv7 package index; package availability is not runtime validation.
start with a terminal, monocle layout, large touch targets and no compositor.
the intended theme is dark mono with a pink accent. a desktop dwm config with
modifier-key shortcuts alone is not a usable touch interface.

use only reviewed components initially, not the full Sxmo service/metapackage
stack. its modem, hardware-key, power and suspend hooks are not validated for
this phone. standalone WM command bindings and keyboard/dock behavior still
need inspection and a real phone test. do not assume a generic Sxmo device
profile fits the Lumia930. this is the X11 path, not sway/Wayland.

input target is `xf86-input-libinput`, but the current Alpine root uses mdev,
not a configured udev device database. check device classification before
assuming libinput hotplug works. an explicit, verified `xf86-input-evdev`
configuration is a possible first fallback; do not blindly replace device
management or run a broad setup script on the working image.

all first installs/configuration should stay in RAM with the existing guarded
storage kernel. no automatic save, boot-image replacement or permanent display
manager. coordinate a local console launch and require visual confirmation on
the phone; successful SSH commands or package installation do not prove X11.
check orientation, touch, keyboard, switching/exiting apps and console recovery.
measure RAM/package size before considering diskless persistence limits.

## GPU is a separate kernel/display task

MSM8974 contains Adreno330. Mesa freedreno supports the A3xx OpenGL family;
Turnip Vulkan is not the A330 driver. that upstream support does not establish
that this board has working clocks, regulators, IOMMU, firmware loading or
native display support.

- audit msm DRM, A3xx GPU, IOMMU, clock/power and firmware dependencies locally.
- prepare a separate RAM-test source/config/output profile. keep the original
  and tested touch/persistence images recoverable. retain the exact MMC bounds
  and prohibitions; do not remove safety checks just to enable graphics.
- investigate GPU probe/render-node operation and offscreen rendering where
  supported. check the actual renderer, not just whether GL software runs.
- native panel/DSI/KMS takeover is additional work. enabling a GPU does not
  automatically replace firmware scanout or accelerate the fbdev X driver.
- move toward the Xorg modesetting/glamor path only when the needed DRM/KMS
  display and GPU paths actually work. no blind DT node enablement or flashing.

battery drain remains unresolved. keep connected tests short and do not treat
USB presence as proof that longer graphics tests are power-neutral.

## references

- [Alpine Xorg setup](https://wiki.alpinelinux.org/wiki/Xorg)
- [Sxmo](https://sxmo.org/)
- [dwm](https://dwm.suckless.org/)
- [svkbd](https://tools.suckless.org/x/svkbd/)
- [Mesa freedreno](https://docs.mesa3d.org/drivers/freedreno.html)
