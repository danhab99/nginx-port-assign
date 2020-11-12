#!/usr/bin/env python3
import json, os, argparse, sys

parser = argparse.ArgumentParser(description='Assigns ports to nginx services')

parser.add_argument('--config', type=str, default='/etc/nginx/npa.json', help='Path to nginx config file')
parser.add_argument('--start', type=int, default=3000, help='Port to start counting at')
parser.add_argument('--dry-run', action="store_true", help="Print actions instead of doing them")
parser.add_argument('--reload', action="store_true", help="Reload nginx")
parser.add_argument('--certbot', action="store_true", help="Run certbot")
parser.add_argument('--hosts', action="store_true", help="Update /etc/hosts")
parser.add_argument('--user', type=str, required=True, help="User to run exports as")

args = parser.parse_args()

print(args)

if not args.dry_run and not os.geteuid() == 0:
    sys.exit("\nOnly root can run this script\n")

TEMPLATE= """server {
  listen 443 ssl http2;

  server_name $SERVICE$$SERVER_NAME$.localhost.xyz;
  server_name $SERVICE$$SERVER_NAME$.$SERVER_EXT$;

  location / {
    proxy_pass http://localhost:$PORT$;
  }
}
"""

def command(cmd):
  if args.dry_run:
    print('COMMAND: ' + cmd)
  else:
    os.system(cmd)

def writeFile(file, content):
  if args.dry_run:
    print('WRITE FILE ' + file + ':\n' + content)
  else:
    with open(file, 'w+') as f:
      f.write(content)

command('mkdir -p /etc/nginx/npa_sites')

if __name__ == '__main__':
  certBotSites = []
  exports = []
  with open(args.config) as f:
    config = json.load(f)
    Port = args.start

    for server_name in config:
      s = server_name.split('.')
      name = s[0]
      ext = s[1]
      for service, enabled in config[server_name].items():
        print(server_name, service)
        dotService = service + '.' if service != '.' else ''
        service = '' if service == '.' else service        
        p = Port if enabled else 0

        nginxConfig = TEMPLATE.replace('$SERVER_NAME$', name)
        nginxConfig = nginxConfig.replace('$SERVICE$', dotService)
        nginxConfig = nginxConfig.replace('$SERVER_EXT$', ext)
        nginxConfig = nginxConfig.replace('$PORT$', str(p))

        ConfigFile = '/etc/nginx/npa_sites/%s_%s_%s.nginx.config' % (service, name, ext)
        writeFile(ConfigFile, nginxConfig)
        exports.append('export NPA_%s_%s_%s_PORT=%d' % (service.upper(), name.upper(), ext.upper(), p))
        
        if enabled:
          command('ln -s %s /etc/nginx/sites-enabled/' % ConfigFile)
          certBotSites.append('-d ' + dotService + server_name)

        Port = Port + 1
  
    writeFile('/home/%s/.npa_exports' % args.user, '\n'.join(exports))
    command('chmod +x /home/%s/.npa_exports' % args.user)

    if args.hosts:
      StartMarker = -1
      EndMarker = -1

      startLines = []
      endLines = []
      npaLines = []
      with open('/etc/hosts', 'r') as f:
        for n, line in enumerate(f):
          if line == "# NPA START HERE\n":
            StartMarker = n
          
          if line == "# NPA END HERE\n":
            EndMarker = n

          if StartMarker < 0:
            startLines.append(line)

          if StartMarker > 0 and EndMarker > 0:
            endLines.append(line)

        if StartMarker < 0:
          print('Start marker not found. Please include # NPA START HERE in your /etc/hosts')
          sys.exit(1)

        if EndMarker < 0:
          print('End marker not found. Please include # NPA END HERE in your /etc/hosts')
          sys.exit(1)

        if StartMarker > EndMarker:
          print('Markers out of order')
          sys.exit(1)

      npaLines.append("# NPA START HERE")
      for server_name in config:
        s = server_name.split('.')
        name = s[0]
        for service in config[server_name]:
          npaLines.append('127.0.0.1 %s%s.localhost.xyz' % (service + '.' if len(service) > 0 else service, name))
      # npaLines.append("# NPA END HERE")

      data = '\n'.join(startLines)
      data = data + '\n'.join(npaLines) + '\n'
      data = data + '\n'.join(endLines)
      writeFile('/etc/hosts', data)

  
  if args.certbot:
    ' '.join(certBotSites)
    command('certbot --nginx ' + ' '.join(certBotSites))

  if args.reload:
    command('nginx -s reload')