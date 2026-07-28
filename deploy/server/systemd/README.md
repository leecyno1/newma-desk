# Newma-Desk 10375 Mod runtimes

These units keep InStock and Orchestra independent from the existing Desk
process while wiring their public origins into the Desk API.

Install the environment file and units with their target paths preserved:

```bash
install -m 0600 mod-runtimes.env /etc/newma-desk-10375/mod-runtimes.env
install -m 0644 newma-desk-10375-instock.service /etc/systemd/system/
install -m 0644 newma-desk-10375-orchestra-api.service /etc/systemd/system/
install -m 0644 newma-desk-10375-orchestra-web.service /etc/systemd/system/
install -d -m 0755 /etc/systemd/system/newma-desk-10375.service.d
install -m 0644 newma-desk-10375.service.d/mod-runtimes.conf \
  /etc/systemd/system/newma-desk-10375.service.d/mod-runtimes.conf
systemctl daemon-reload
```

The drop-in must remain under `newma-desk-10375.service.d/`; copying it as a
standalone unit will not inject the external runtime URLs into the Desk API.
