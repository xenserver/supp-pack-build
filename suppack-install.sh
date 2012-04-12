#!/bin/sh

v=`rpm -q --qf '%{RELEASE}' xcp-python-libs`
if [ $? -eq 0 ]; then
  [ ${v#xs} -ge 45 ] && exec ${0%.sh} $*
fi

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

split()
{
  local oldifs="$IFS"
  IFS="$1"

  set -- $2
  echo $@

  IFS="$oldifs"
}

arc_cmp()
{
  local l=$(echo "$1" | tr '-' '.')
  local r=$(echo "$2" | tr '-' '.')

  expr "$l" : '-\?[0-9]\+$' >/dev/null
  local l_is_int=$?
  expr "$r" : '-\?[0-9]\+$' >/dev/null
  local r_is_int=$?

  if [ $l_is_int -eq 0 -a $r_is_int -eq 0 ]; then
    echo $((l-r))
  else
    ver_cmp $l $r
  fi
}

ver_cmp()
{
  local l="$1"
  local r="$2"

  local oldifs="$IFS"
  IFS=" "
  local l_a=( $(split . $l) )
  local r_a=( $(split . $r) )
  IFS="$oldifs"
  local val

  local n=${#l_a[@]}
  [ $n -gt ${#r_a[@]} ] && n=${#r_a[@]}
  for (( i = 0 ; i < $n ; i++ ))
  do
    val=$(arc_cmp ${l_a[$i]} ${r_a[$i]})
    [ $val -ne 0 ] && echo $val && return
  done

  echo $((${#l_a[@]}-${#r_a[@]}))
}

ver_eval()
{
  local need_test=$1
  local need_version="$2"
  local have_version="$3"

  val=$(ver_cmp $have_version $need_version)
  test $val -$need_test 0
}

dependency_satisfied()
{
  local need_test=$1
  local need_version="$2"
  local need_build=$(echo "$3" | tr -cd '0-9')
  local have_version="$4"
  local have_build=$(echo "$5" | tr -cd '0-9')

  if [ -n "$need_build" ]; then
    need_version="$2.$need_build"
    if [ -n "$have_build" ]; then
      have_version="$4.$have_build"
    else
      have_version="$4.-1"
    fi
  fi

  ver_eval $need_test $need_version $have_version
  ret=$?

  [ $ret -lt 0 ] && ret=100
  return $ret
}


installed_repos_dir=/etc/xensource/installed-repos

if [ ! -r XS-REPOSITORY ]; then
  echo "FATAL: Cannot open XS-REPOSITORY" >&2
  exit 1
fi


if [ ! -r XS-PACKAGES ]; then
  echo "FATAL: Cannot open XS-PACKAGES" >&2
  exit 1
fi

repo_el=`xml_el repository 1 <XS-REPOSITORY`
originator=`echo "$repo_el" | xml_attr originator`
name=`echo "$repo_el" | xml_attr name`
product=`echo "$repo_el" | xml_attr product`
version=`echo "$repo_el" | xml_attr version`
build=`echo "$repo_el" | xml_attr build`
description=`xml_el description <XS-REPOSITORY | xml_cdata`
identifier="$originator:$name"

. /etc/xensource-inventory

# check compatibility
if [ "$PRODUCT_BRAND" != "$product" ]; then
  echo "Error: Repository is not compatible with installed product ($product expected)" >&2
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
fi

# check if installed already
if [ -d $installed_repos_dir/$identifier ]; then
  while :; do
    echo -n "Warning: '$description' is already installed, do you want to continue? (Y/N) "
    read prompt
    case $prompt in
      y|Y)
        break;;
      n|N)
	exit 3;;
    esac
  done
fi

oldifs="$IFS"
IFS='
'
# check dependencies
fatal=0
error=0
for requires in `xml_el requires <XS-REPOSITORY`
do
  need_originator=`echo "$requires" | xml_attr originator`
  need_name=`echo "$requires" | xml_attr name`
  need_test=`echo "$requires" | xml_attr test`
  need_version=`echo "$requires" | xml_attr version`
  need_build=`echo "$requires" | xml_attr build`

  need_identifier="$need_originator:$need_name"
  if [ ! -r $installed_repos_dir/$need_identifier/XS-REPOSITORY ]; then
    echo "FATAL: missing dependency $need_identifier" >&2
    fatal=1
  else
    have_repo_el=`xml_el repository 1 <$installed_repos_dir/$need_identifier/XS-REPOSITORY`
    have_originator=`echo "$have_repo_el" | xml_attr originator`
    have_name=`echo "$have_repo_el" | xml_attr name`
    have_product=`echo "$have_repo_el" | xml_attr product`
    have_version=`echo "$have_repo_el" | xml_attr version`
    have_build=`echo "$have_repo_el" | xml_attr build`
    if ! dependency_satisfied $need_test $need_version "$need_build" $have_version $have_build; then
      echo "Error: unsatisfied dependency $need_identifier $need_test $need_version${need_build:+-$need_build}" >&2
      error=1
    fi
  fi
done

[ $fatal -eq 1 ] && exit 1
if [ $error -eq 1 ]; then
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
fi

fatal=0
for package in `xml_el package <XS-PACKAGES`
do
  label=`echo "$package" | xml_attr label`
  type=`echo "$package" | xml_attr type`
  md5sum=`echo "$package" | xml_attr md5`
  file=`echo "$package" | xml_cdata`
  reference=`echo "$md5sum  $file"`

  if [ -r "$file" ]; then
    if [ "`md5sum $file`" != "$reference" ]; then
      echo "FATAL: MD5 mismatch on $file (expected $md5sum)" >&2
      fatal=1
    fi
  else
      echo "FATAL: $file missing" >&2
      fatal=1
  fi
  case "$type" in
    *rpm)
      # check if this version is already installed
      install=1
      rpm_name=$(rpm -q --qf %{NAME} -p $file)
      ver=$(rpm -q --qf %{VERSION}-%{RELEASE} $rpm_name)
      if [ $? -eq 0 ]; then
        new_ver=$(rpm -q --qf %{VERSION}-%{RELEASE} -p $file)
        if [ "$ver" = "$new_ver" ]; then
	  install=0
          doc_rpms="$doc_rpms $file"
	fi
      fi
      if [ $install -eq 1 ]; then
        rpms="$rpms $file"
      fi;;
  esac
done
IFS="$oldifs"

[ $fatal -eq 1 ] && exit 1
echo -e "Installing '$description'...\n"

for rpm in $rpms $doc_rpms; do
  eula=`rpm2cpio $rpm | cpio -i --to-stdout --quiet *EULA`
  if [ -n "$eula" ]; then
    echo "$eula"
    while :; do
      echo -n "Accept? (Y/N) "
      read prompt
      case $prompt in
        y|Y)
          break;;
        n|N)
	  exit 4;;
      esac
    done
  fi
done

[ -z "$rpms" ] || rpm -Uhv $rpms
ret=$?

if [ $ret -eq 0 ]; then
  mkdir -p $installed_repos_dir/$identifier
  cp -fp XS-PACKAGES XS-REPOSITORY $installed_repos_dir/$identifier

  /opt/xensource/libexec/set-dom0-memory-target-from-packs

  [ -r /etc/xensource-inventory ] && . /etc/xensource-inventory
  [ -n "$INSTALLATION_UUID" ] && xe host-refresh-pack-info host-uuid=$INSTALLATION_UUID
  echo "Pack installation successful."
else
  echo "FATAL: packages failed to install" >&2
fi

exit $ret
