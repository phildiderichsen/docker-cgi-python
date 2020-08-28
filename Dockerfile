# Docker file for python simple webservice build

FROM ubuntu:18.04

#ENV LC_ALL da_DK.UTF-8
#ENV LANG da_DK.UTF-8
#ENV LANGUAGE da_DK.UTF-8

RUN apt-get update
RUN apt-get -y install apache2 vim

# Python3.8
RUN apt-get -y install python3.5 python-pip

# Copy Python dependencies file to the working directory
COPY requirements.txt .

# install dependencies
RUN python3 -m pip install -r requirements.txt


# Http settings
ENV APACHE_RUN_USER www-data
ENV APACHE_RUN_GROUP www-data
ENV APACHE_LOG_DIR /var/log/apache2
ENV APACHE_PID_FILE /var/run/apache2.pid
ENV APACHE_RUN_DIR /var/run/apache2
ENV APACHE_LOCK_DIR /var/lock/apache2
RUN mkdir -p $APACHE_RUN_DIR $APACHE_LOCK_DIR $APACHE_LOG_DIR

RUN mkdir -p /production/www/cgi-bin
RUN mkdir -p /production/www/lib
COPY cgi-bin /production/www/cgi-bin
COPY lib /production/www/lib
COPY apache2 /etc/apache2
RUN ln -s /etc/apache2/mods-available/cgi.load /etc/apache2/mods-enabled/cgi.load

EXPOSE 80

ENTRYPOINT [ "/usr/sbin/apache2" ]
CMD ["-D", "FOREGROUND"]
