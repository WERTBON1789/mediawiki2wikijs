# mediawiki2wikijs
A docker container to migrate mediawiki to wikijs

# Initial steps
First, you need to copy example.env to .env and add your settings in there so docker-compose can use the contents.
Second, you also need to copy the example.username_mapping.json to username_mapping.json and add your usernames.

For example, if you have a user in your mediawiki, with only their first name, but you want to change their username to their full name, or sirname
you can just add the entry in there, and the script will do the renaming for you.
Also, if you import users from an LDAP server, and their names differ from the same people in your mediawiki instance, you can map these names
to the names from the LDAP server, so you don't have duplicate users.

You need docker-compose installed.
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

Keep in mind that you need to provide your openvpn files in a directory called openvpn in the same directory as the docker-compose.yml file
