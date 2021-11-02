#!/bin/bash
PYTHON_CMD=''

check_binary() {
    HAS_VAR_NAME=HAS_$2
    CMD_VAR_NAME=$2_CMD
    if [ "$(eval echo \${${HAS_VAR_NAME}})" = "0" ]; then return; fi
    which $1 2>/dev/null
    RET_CODE=$?
    eval "${HAS_VAR_NAME}=${RET_CODE}"
    if [ ${RET_CODE} -eq 0 ]; then eval "${CMD_VAR_NAME}=$1"; fi
}

check_binary python3 PYTHON3
check_binary python2.6 PYTHON2_6
check_binary python26 PYTHON26
check_binary python2.7 PYTHON2_7
check_binary python27 PYTHON27
check_binary python2 PYTHON2

which python 2>/dev/null
if [ $? -eq 0 ]; then
  PYTHON_VERSION=$(python --version 2>&1 | grep -Po '(?<=Python )[\d]')
  eval "HAS_PYTHON${PYTHON_VERSION}=0"
  eval "PYTHON${PYTHON_VERSION}_CMD='python'"
fi

check_binary apt-get APT
check_binary yum YUM
check_binary dnf DNF
check_binary zypper ZYPP

check_install_code() {
    if [ $1 -ne 0 ]
    then
        echo "WARNING: Could not install the $2, this may cause the patching operation to fail." >&2
    fi
}

get_env_var_hash_key() {
    # Get an environment variable that is a dictionary and retrieve the provided key.
    # $1 is the environment variable.
    # $2 is the dictionary key.
    # $3 is the python version & command found on instance.
    result=$(echo -e "import json\nimport os\nprint(json.loads(os.environ[\"$1\"])[\"$2\"])" | $3)
    if [ -z "$result" ]
    then
        exit 1
    fi
    echo $result
}

get_creds() {
  check_binary curl CURL
  check_binary wget WGET
  TOKEN_HEADER=":"
  if [ $HAS_CURL -eq 0 ]
  then
      TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -m 10 -f -s -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
      if [ -n "$TOKEN" ]; then TOKEN_HEADER="X-aws-ec2-metadata-token: $TOKEN"; fi
      IAM_ROLE=`curl -H "$TOKEN_HEADER" -m 10 -f -s http://169.254.169.254/latest/meta-data/iam/security-credentials`
      export CREDENTIALS=`curl -H "$TOKEN_HEADER" -m 10 -f -s http://169.254.169.254/latest/meta-data/iam/security-credentials/$IAM_ROLE`
  elif [ $HAS_WGET -eq 0 ]
  then
      TOKEN="`wget -qO- -T 10 --method PUT --header "X-aws-ec2-metadata-token-ttl-seconds: 21600" http://169.254.169.254/latest/api/token`"
      if [ -n "$TOKEN" ]; then TOKEN_HEADER="X-aws-ec2-metadata-token: $TOKEN"; fi
      IAM_ROLE="`wget -qO- -T 10 --header "$TOKEN_HEADER" http://169.254.169.254/latest/meta-data/iam/security-credentials`"
      export CREDENTIALS="`wget -qO- -T 10 --header "$TOKEN_HEADER" http://169.254.169.254/latest/meta-data/iam/security-credentials/$IAM_ROLE`"
  fi

  if [ -z "$CREDENTIALS" ]; then return 1; fi
  export AWS_ACCESS_KEY_ID=$(get_env_var_hash_key "CREDENTIALS" "AccessKeyId" $1)
  export AWS_SECRET_ACCESS_KEY=$(get_env_var_hash_key "CREDENTIALS" "SecretAccessKey" $1)
  export AWS_SESSION_TOKEN=$(get_env_var_hash_key "CREDENTIALS" "Token" $1)
  export AWS_CREDENTIAL_EXPIRATION=$(get_env_var_hash_key "CREDENTIALS" "Expiration" $1)
}

CANDIDATES=( $HAS_PYTHON2_6 $HAS_PYTHON26 $HAS_PYTHON2_7 $HAS_PYTHON27 $HAS_PYTHON2 )
HAS_ANY_PYTHON2=1
for CANDIDATE in "${CANDIDATES[@]}"
do
    if [ $CANDIDATE -eq 0 ]
    then
        HAS_ANY_PYTHON2=0
    fi
done

check_instance_is_debian_8() {
    if [ -f /etc/os-release ] && grep "ID=debian" /etc/os-release >/dev/null; then
        IS_DEBIAN=true
        if grep 'VERSION_ID="8"' /etc/os-release >/dev/null; then
            IS_DEBIAN_8=true
        fi
    fi
}
check_if_debian_signing_key_exist() {
    MISSING_KEY=0
    if [ "$HAS_APT_KEY" = "0" ] && (apt-key list | grep -w 8AE22BA9) > /dev/null; then
      MISSING_KEY=1
    fi
}
prepare_instance_if_debian_8() {
    KEY_IMPORTED=0
    COMMENTED_OUT_BACKPORTS=0
    check_instance_is_debian_8
    if [ ! -z $IS_DEBIAN ] && [ ! -z $IS_DEBIAN_8 ]; then
        HAS_APT_KEY=1
        check_binary apt-key APT_KEY
        check_if_debian_signing_key_exist
        if [ "$HAS_APT_KEY" = "0" ]; then
            if [ "$MISSING_KEY" = "0" ]; then
                apt-key adv --keyserver keyserver.ubuntu.com --recv-keys AA8E81B4331F7F50 >/dev/null 2>&1
                KEY_IMPORTED=1
                echo "Imported missing signing key: AA8E81B4331F7F50"
            else
                echo "Skip to synchronize pakcage index for DEBIAN 8 instance. "
            fi
        else
            echo "Could not locate apt-key."
        fi
        if [ -f /etc/apt/sources.list.d/backports.list ]; then
            if grep -i "^#[[:space:]]*deb http://cloudfront.debian.net/debian jessie-backports main" /etc/apt/sources.list.d/backports.list >/dev/null;then
                echo "Already commented out jessie backports"
            else
                sed -e "/jessie-backports main/ s/^#*/#/" -i /etc/apt/sources.list.d/backports.list
                COMMENTED_OUT_BACKPORTS=1
            fi
        fi
        echo "Synchronizing pakcage index for DEBIAN 8 instance"
        apt-get update >/dev/null
    fi
}

clean_up_instances_if_debian_8() {
    if [ "$KEY_IMPORTED" = "1" ]; then
        apt-key del 8AE22BA9 > /dev/null
    fi
    if [ "$COMMENTED_OUT_BACKPORTS" = "1" ]; then
        sudo sed -e '/jessie-backports main/ s/^#//g' -i /etc/apt/sources.list.d/backports.list
    fi
}

if [ $HAS_APT -eq 0 -a $HAS_PYTHON3 -eq 0 ]
then
    PYTHON_CMD=${PYTHON3_CMD}
    prepare_instance_if_debian_8
    apt-get install python3-apt -y
    check_install_code $? "python3-apt"

elif  [ $HAS_DNF -eq 0 ] && [ $HAS_PYTHON2 -eq 0 -o $HAS_PYTHON3 -eq 0 ]
then
    if [ $HAS_PYTHON2 -eq 0 ]
    then
        PYTHON_CMD=${PYTHON2_CMD}
    elif [ $HAS_PYTHON3 -eq 0 ]
    then
        PYTHON_CMD=${PYTHON3_CMD}
    fi

elif [ $HAS_YUM -eq 0 -a $HAS_ANY_PYTHON2 -eq 0 ]
then

    HAS_COMPATIBLE_YUM=false

    INSTALLED_PYTHON=( $PYTHON2_7_CMD $PYTHON27_CMD $PYTHON2_CMD $PYTHON2_6_CMD $PYTHON26_CMD  )
    for TEST_PYTHON_CMD in "${INSTALLED_PYTHON[@]}"
    do
        ${TEST_PYTHON_CMD} -c "import yum" 2>/dev/null
        if [ $? -ne 0 ]; then
            echo "Unable to import yum module on $TEST_PYTHON_CMD"
        else
            PYTHON_CMD=${TEST_PYTHON_CMD}
            HAS_COMPATIBLE_YUM=true
            break
        fi
    done
    if ! $HAS_COMPATIBLE_YUM; then
        echo "Unable to import yum module, please check version compatibility between Yum and Python"
        exit 1
    else
        YUM_VERSION=$(yum --version 2>/dev/null | sed -n 1p)
        echo "Using Yum version: $YUM_VERSION"
    fi

elif [ $HAS_ZYPP -eq 0 -a $HAS_PYTHON3 -eq 0 ]
then
    PYTHON_CMD=${PYTHON3_CMD}
elif [ $HAS_ZYPP -eq 0 -a $HAS_PYTHON2 -eq 0 ]
then
    PYTHON_CMD=${PYTHON2_CMD}
else
    echo "An unsupported package manager and python version combination was found."
    if [ $HAS_DNF -eq 0 ]
    then
        echo "Dnf requires Python2 or Python3 to be installed."
    elif [ $HAS_YUM -eq 0 ]
    then
        echo "Yum requires Python2 to be installed."
    elif [ $HAS_APT -eq 0 ]
    then
        echo "Apt requires Python3 to be installed."
    elif [ $HAS_ZYPP -eq 0 ]
    then
        echo "ZYpp requires Python2 or Python3 to be installed."
    fi
    echo "Python3=$HAS_PYTHON3, Python2=$HAS_ANY_PYTHON2, Yum=$HAS_YUM, Apt=$HAS_APT, Zypper=$HAS_ZYPP, Dnf=$HAS_DNF"
    echo "Exiting..."
    exit 1
fi

echo "Using python binary: '${PYTHON_CMD}'"
PYTHON_VERSION=$(${PYTHON_CMD} --version  2>&1)
echo "Using Python Version: $PYTHON_VERSION"

if [[ ! $AWS_SSM_INSTANCE_ID =~ ^mi-.* ]] && [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" || -z "$AWS_SESSION_TOKEN" || -z "$AWS_CREDENTIAL_EXPIRATION" ]]
then
    # Get IAM Credentials if not present on an instance already
    get_creds $PYTHON_CMD || echo "Unable to pull security credentials from Instance Metadata Service, attempting to use local credentials file"
fi

echo '
import errno
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
import sys

tmp_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations/")
reboot_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-194/")
reboot_with_failure_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-195/")
reboot_with_dependency_failure_dir = os.path.abspath("/var/log/amazon/ssm/patch-baseline-operations-reboot-196/")

# initialize logging
LOGGER_FORMAT = "%(asctime)s %(name)s [%(levelname)s]: %(message)s"
LOGGER_DATEFORMAT = "%m/%d/%Y %X"
LOGGER_LEVEL = logging.INFO
LOGGER_STREAM = sys.stdout

logging.basicConfig(format=LOGGER_FORMAT, datefmt=LOGGER_DATEFORMAT, level=LOGGER_LEVEL, stream=LOGGER_STREAM)
logger = logging.getLogger()

ERROR_CODE_MAP = {
    151: "%s sha256 check failed, should be %s, but is %s",
    152: "Unable to load and extract the content of payload, abort.",
    154: "Unable to create dir: %s",
    155: "Unable to extract tar file: %s.",
    156: "Unable to download payload: %s."
}

# All the existing regions after CPT/MXP build
# We will change the payload buckets that customers point to in future new region
OLD_BUCKET_REGIONS = ["ap-east-1", "us-gov-east-1", "us-gov-west-1", "cn-northwest-1", "cn-north-1", "ca-central-1",
             "ap-southeast-2", "ap-southeast-1", "us-west-1", "us-west-2", "ap-northeast-1", "eu-west-2", "ap-northeast-2",
             "us-east-1", "sa-east-1", "eu-central-1", "eu-west-1", "us-east-2", "eu-west-3", "ap-south-1", "eu-north-1",
             "me-south-1", "af-south-1", "eu-south-1", "ap-northeast-3"]
# When an install occurs and the instance needs a reboot, the agent restarts our plugin.
# Check if these folders exist to know how to succeed or fail a command after a reboot.
# DO NOT remove these files here. They are cleaned in the common startup.
if os.path.exists(reboot_dir) or os.path.exists(reboot_with_failure_dir) or os.path.exists(reboot_with_dependency_failure_dir):
    # Reload Payload so that we remove reboot directories
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)

def create_dir(dirpath):
    dirpath = os.path.abspath(dirpath)
    if not os.path.exists(dirpath):
        try:
            os.makedirs(dirpath)
        except OSError as e:  # Guard against race condition
            if e.errno != errno.EEXIST:
                raise e
        except Exception as e:
            logger.error("Unable to create dir: %s", dirpath)
            logger.exception(e)
            abort(154, (dirpath))

def use_curl():
    output, has_curl = shell_command(["which", "curl"])
    if has_curl == 0:
        return True
    else:
        return False

def download_to(url, file_path):
    curl_present = use_curl()
    logger.info("Downloading payload from %s", url)
    if curl_present:
        output, curl_return = shell_command(["curl", "-f", "-o", file_path, url])
    else:
        output, curl_return = shell_command(["wget", "-O", file_path, url])

    if curl_return != 0:
        download_agent = "curl" if curl_present else "wget"
        logger.error("Error code returned from %s is %d", download_agent, curl_return)
        abort(156, (url))

def download(url):
    if use_curl():
        url_contents, curl_return = shell_command(["curl", url])
    else:
        url_contents, curl_return = shell_command(["wget", "-O-", url])
    if curl_return == 0:
        return url_contents
    else:
        raise Exception("Could not curl %s" % url)

def extract_tar(path):
    path = os.path.abspath(path)
    try:
        f = tarfile.open(path, "r|gz")
        f.extractall()
    except Exception as e:
        logger.error("Unable to extract tar file: %s.", path)
        logger.exception(e)
        abort(155, (path))
    finally:
        f.close()

def shell_command(cmd_list):
    with open(os.devnull, "w") as devnull:
        p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=devnull)
        (std_out, _) = p.communicate()
        if not type(std_out) == str:
            std_out = std_out.decode("utf-8")
        return (std_out, p.returncode)

def abort(error_code, params = ()):
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    sys.stderr.write(ERROR_CODE_MAP.get(error_code) % params)
    sys.exit(error_code)

def sha256_checksum(filename):
    sha256_hash = hashlib.sha256()
    with open(filename,"rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096),b""):
            sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().upper()

# cd into the temp directory
create_dir(tmp_dir)
os.chdir(tmp_dir)

region = os.environ["AWS_SSM_REGION_NAME"]

# main logic
# Old bucket location
s3_bucket = "aws-ssm-%s"%(region)
s3_prefix = "patchbaselineoperations/linux/payloads"
payload_name = "patch-baseline-operations-1.80.tar.gz"
payload_sha256 = "321AEC321520744D4D60E51251342E1801BAF7B8C8D7B0F9566CBFC17A0DE0CE"

if region == "me-south-1":
    s3_bucket = "aws-patch-manager-me-south-1-a53fc9dce"
elif region == "af-south-1":
    s3_bucket = "aws-patch-manager-af-south-1-bdd5f65a9"
elif region == "eu-south-1":
    s3_bucket = "aws-patch-manager-eu-south-1-c52f3f594"
elif region == "ap-northeast-3":
    s3_bucket = "aws-patch-manager-ap-northeast-3-67373598a"

# New bucket location
# Currently only commerical regions buckets are reserved
if region not in OLD_BUCKET_REGIONS and not region.startswith(("cn-","us-gov-")):
    s3_bucket = "aws-patch-manager-%s" % (region)

# download payload file and do signature verification
# For new regions after CPT/MXP we will utilize s3 transfer acceleration access point
# China and Gov region do not support this feature
region_to_interpolate = region
if region.startswith("cn-"):
    url_template = "https://s3.%s.amazonaws.com.cn/%s/%s"
elif region.startswith("us-gov-"):
    url_template = "https://s3-fips-%s.amazonaws.com/%s/%s"
elif region in OLD_BUCKET_REGIONS:
    url_template = "https://s3.dualstack.%s.amazonaws.com/%s/%s"
else:
    url_template = "https://%s%s.s3-accelerate.dualstack.amazonaws.com/%s"
    region_to_interpolate = ""

download_to(url_template % (region_to_interpolate, s3_bucket, os.path.join(s3_prefix, payload_name)), payload_name)

# payloads are the actual files to be used for linux patching
payloads = []
try:
    sha256_code = sha256_checksum(payload_name)
    if not sha256_code == payload_sha256:
        error_msg = "%s sha256 check failed, should be %s, but is %s" % (payload_name, payload_sha256, sha256_code)
        logger.error(error_msg)
        abort(151, (payload_name, payload_sha256, sha256_code))
    extract_tar(payload_name)
    # Change owner & group to be root user for the payload.
    shell_command(["chown", "-R", "0:0", tmp_dir])
except Exception as e:
    error_msg = "Unable to load and extract the content of payload, abort."
    logger.error(error_msg)
    logger.exception(e)
    abort(152)


# Document parameters.
import sys
try:
    import common_startup_entrance
    common_startup_entrance.execute("os_selector", "PatchLinux", "{{SnapshotId}}",\
            "{{Operation}}", "{{InstallOverrideList}}", \
            "{{RebootOption}}", "{{BaselineOverride}}")
except Exception as e:
    error_code = 156
    if hasattr(e, "error_code") and type(e.error_code) == int:
        error_code = e.error_code;
    logger.exception(e)
    sys.exit(error_code)
    

' | $PYTHON_CMD

RETURN_CODE=$?

clean_up_instances_if_debian_8

exit $RETURN_CODE
