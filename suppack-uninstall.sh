#!/bin/sh

xml_el()
{
  local el=$1
  local level=0
  local max_level=0
  [ -n "$2" ] && max_level=$2
  local line

  while read line
  do
    while [ -n "$line" ]
    do
      cdata=`expr "$line" : '\([^<]*\)'`
      if [ -n "$cdata" ]; then
	[ $level -gt $max_level ] && echo -n "$cdata"
	line=`expr "$line" : '[^<]*\(.*\)'`
      fi
      tag=`expr "$line" : '\(<[^<>]*>\)'`
      if [ -n "$tag" ]; then
	line=`expr "$line" : '<[^<>]*>\(.*\)'`

	case "$tag" in
	  \<$el/\>|\<$el\ */\>)
	    echo "$tag";;
	  \<$el\>|\<$el\ *\>)
	    level=$((level+1))
	    echo -n "$tag";;
	  "</$el>")
	    level=$((level-1))
	    echo -n "$tag"
	    [ $level -le $max_level ] && echo;;
	  *)
	    [ $level -gt $max_level ] && echo -n "$tag";;
	  esac
      fi
    done
  done
}

xml_attr()
{
  local attr=$1  

  sed -ne "s#.*$attr=\"\([^\"]*\)\".*#\1#p"
}

xml_cdata()
{
  sed -ne 's#<[^<>]*>\([^<]*\)<[^<>]*>#\1#p'
}


identifier="$1"
if [ -z "$identifier" ]; then
  echo "Usage: $0 identifier" >&2
  exit 1
fi

installed_repos_dir=/etc/xensource/installed-repos

if [ ! -d $installed_repos_dir/$identifier ]; then
  echo "FATAL: Pack $identifier is not installed" >&2
  exit 1
fi

if [ ! -r $installed_repos_dir/$identifier/XS-REPOSITORY ]; then
  echo "FATAL: Cannot open XS-REPOSITORY" >&2
  exit 1
fi

if [ ! -r $installed_repos_dir/$identifier/XS-PACKAGES ]; then
  echo "FATAL: Cannot open XS-PACKAGES" >&2
  exit 1
fi

repo_el=`xml_el repository 1 <$installed_repos_dir/$identifier/XS-REPOSITORY`
originator=`echo "$repo_el" | xml_attr originator`
name=`echo "$repo_el" | xml_attr name`
description=`xml_el description <$installed_repos_dir/$identifier/XS-REPOSITORY | xml_cdata`
identifier="$originator:$name"

# check if any other pack depends on us
fatal=0
for dir in $installed_repos_dir/*
do
  pack=`basename $dir`
  [ "$pack" = "$identifier" ] && continue
  [ -r $dir/XS-REPOSITORY ] || continue

  oldifs="$IFS"
  IFS='
'
  for requires in `xml_el requires <$dir/XS-REPOSITORY`
  do
    need_originator=`echo "$requires" | xml_attr originator`
    need_name=`echo "$requires" | xml_attr name`

    need_identifier="$need_originator:$need_name"
    if [ "$need_identifier" = "$identifier" ]; then
      echo "Error: $identifier is required by $pack" >&2
      fatal=1
    fi
  done
  IFS="$oldifs"
done

[ $fatal -eq 1 ] && exit 1

echo -e "Uninstalling '$description'\n"

while :; do
  echo -n "Do you want to continue? (Y/N) "
  read prompt
  case $prompt in
    y|Y)
      break;;
    n|N)
      exit 2;;
  esac
done

oldifs="$IFS"
IFS='
'
for package in `xml_el package <$installed_repos_dir/$identifier/XS-PACKAGES`
do
  type=`echo "$package" | xml_attr type`
  label=`echo "$package" | xml_attr label`

  case "$type" in *rpm) rpms="$label $rpms";; esac
done
IFS="$oldifs"

rpm -e $rpms
ret=$?

if [ $ret -eq 0 ]; then
  rm -rf $installed_repos_dir/$identifier

  /opt/xensource/libexec/set-dom0-memory-target-from-packs

  [ -r /etc/xensource-inventory ] && . /etc/xensource-inventory
  [ -n "$INSTALLATION_UUID" ] && xe host-refresh-pack-info host-uuid=$INSTALLATION_UUID
else
  echo "FATAL: packages failed to uninstall" >&2
fi

exit $ret
