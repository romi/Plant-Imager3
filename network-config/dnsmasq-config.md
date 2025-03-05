# Setup dns and dhcp server with `dnsmasq`

Setting up the dns server and the dhcp serer with dnsmasq
on the `plant-imager` raspberry pi which is also doing creating
the Wi-Fi network for the cameras will allow us to 
give static ip address leases for the different computers
as well as access them via their hostname rather than just their
ip addresses.

## Install requirements

For this installation `dnsmasq` and `resolvconf` are required.

To install `dnsmasq`:
```shell
sudo apt install dnsmasq
```

To install `resolvconf` we can use [openresolv](https://wiki.archlinux.org/title/Openresolv)
which is an implementatiion of `resolvconf.`
```shell
sudo apt install openresolv
```


## External resources

This is based on the following resources:
 - https://doc.ubuntu-fr.org/configuration_serveur_dns_dhcp
 - https://wiki.archlinux.org/title/Dnsmasq
 - https://www.linuxtricks.fr/wiki/dnsmasq-le-serveur-dns-et-dhcp-facile-sous-linux