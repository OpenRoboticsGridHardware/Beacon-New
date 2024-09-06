# Beacon-New
  openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
  129  ls
  130  openssl x509 -in cert.pem -text -noout
  131  openssl rsa -in key.pem -check