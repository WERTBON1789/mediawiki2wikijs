# mediawiki2wikijs
A docker container to migrate mediawiki to wikijs

# Initial steps
First, you need to copy example.env to .env and add your settings in there so docker-compose can use the contents.

You also need docker-compose installed.
To install it,
just follow the docker docs article about it for your platform:
https://docs.docker.com/compose/install/

Or, if you're on Arch Linux, just:
```
$ sudo pacman -Sy docker-compose
```

# Start the container

To start the container:

```
# docker-compose up -d
```

If your mediawiki installation is only accessable via a OpenVPN connection, you can also use the openvpn.docker-compose.yml:

```
# docker-compose -f openvpn.docker-compose.yml up -d
```
