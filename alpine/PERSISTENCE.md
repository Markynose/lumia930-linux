# diskless persistence

experimental lumia930 Data-only kernel, tested by RAM boot and installed-menu
boot. do not use an unrestricted MMC kernel or install an untested candidate.
Windows stays default. no partitioning, formatting or Windows boot-file changes.

## use

on the desktop or thinkpad, with the phone USB cable attached:

```sh
lumia-usb
ssh lumia930
```

inside the phone:

```sh
apk add curl htop
lumia-save
```

or run `lumia-save` on the host to invoke the same phone command through the
pinned SSH alias. the host needs no phone image, server private key or backup.

`lumia-save` commits `/etc`, `/root` except `/root/.cache`, `/usr/local`, the
installed official signed package set and apk world. the running root remains
RAM-backed. changes elsewhere, unsaved changes, running processes, clocks and
mounts are not persisted. base recovery packages are retained at boot.

boot restores packages and selected files into RAM without internet, before
USB/SSH start. Data is mounted read-only for restoration, then unmounted.
normal operation does not leave a Windows volume mounted. saving stages and
verifies in RAM, temporarily mounts Data read-write, writes a new immutable
generation, verifies the copy, syncs and cleanly unmounts. do not unplug power
or reset during saving. wait for the host command to return successfully.

## scope and limits

- store: `linux/alpine` in the existing NTFS Data partition, not EFIESP.
- manual commit only; no automatic shutdown save.
- initial save or newly installed package versions may need internet to fill
  the cache. after restoration, an unchanged package set can be saved offline.
- exact installed versions must still be available on the official mirrors or
  already be in the RAM cache. virtual/local/third-party packages are not a
  supported initial workflow. never bypass signature checks.
- configuration tar:16MiB uncompressed maximum. total snapshot:128MiB maximum.
- previous generations remain available; no automatic deletion. invalid newest
  checksums fall back to the previous valid generation. package/configuration
  application is not a transactional whole-root rollback.
- SHA256 detects corruption, not malicious modification of the saved config.
  snapshots contain private configuration and phone SSH host credentials.
  do not publish or copy them into a public repository.
- the bounded kernel denies normal MMC writes outside Data, erase/security/
  boot-partition commands, raw MMC ioctls and CQE. it verifies cache-off, user
  hardware partition and512-byte sectors. this is not hardware write protection
  or a claim that privileged raw MMIO cannot bypass software protection.
- NTFS read-write mounting still changes its journal/allocation metadata and
  carries power-loss/driver risk. there is no force mount or repair fallback.

keep the independent original RAM image and a pre-write Data backup on the PC.
the installed image now restores saved state from Data. the previous image
is also backed up on the phone at
`C:\Data\linux\alpine\boot-pre-persistence.img`.
a bad saved configuration can break services; retain fastboot/recovery access
and the Windows default path. restore the previous image through Windows only
when deliberately reverting:

```bat
copy /b /y C:\Data\linux\alpine\boot-pre-persistence.img C:\EFIESP\alpine\boot.img
fc /b C:\Data\linux\alpine\boot-pre-persistence.img C:\EFIESP\alpine\boot.img
```
