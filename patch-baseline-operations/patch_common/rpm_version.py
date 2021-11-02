import re

# matches things that are NOT: number, letter, or tilde.
VERSION_SEPARATOR = re.compile(r"^[^a-zA-Z0-9~]+")
NUMBERS = re.compile(r"([0-9]+)(.*)")
LETTERS = re.compile(r"([a-zA-Z]+)(.*)")
# This separator is for identifying the version versus release portion of an
# edition. For example, "3.2.1-2.1.0" has a version of "3.2.1" and release of "2.1.0"
# Without separating on '-' and testing version followed by release, the following test
# will faile. compare("3.0.2-95.24.1", "3.0-95.21.1") because 2 will be compared to 95
# but version takes precedence over release.
VERSION_RELEASE_SEPARATOR = re.compile(r".+-.+")

def compare(left, right):
    """
    Implementation of RPMs version comparison algorithm, coded in RPMs lib/rpmvercmp.c. The algorithm is fairly
    quirky, but this attempt to follow it fully. A quick sanity check is that this must return the same thing as
    "rpmdev-vercmp left right". rpmdev-vercmp is available in the repos for AL and other yum based distros,
    as part of rpmdevtools.

    https://github.com/rpm-software-management/rpm/blob/c7e711bba58374f03347c795a567441cbef3de58/lib/rpmvercmp.c

    :param left: 1 if newer
    :param right: -1 if newer
    :return: 1 if left is newer, 0 if equal, -1 if right is newer
    """
    if VERSION_RELEASE_SEPARATOR.match(left) and VERSION_RELEASE_SEPARATOR.match(right):
        (left_version, left_release) = left.split("-", 1)
        (right_version, right_release) = right.split("-", 1)
        
        version_result = __iterative_compare(left_version, right_version)
        edition_result = version_result if version_result != 0 else __iterative_compare(left_release, right_release)
        return edition_result
    else:
        return __iterative_compare(left, right)

def __iterative_compare(left, right):
    """
    Method for walking values from left to right and comparing each one individually.
    This was previously the compare() method.
    :param left is the original value, right is the one being compared.
    :return 1 if left is newer, 0 if equal, -1 if right is newer
    """
    if left == right:
        return 0
    remain_left = left
    remain_right = right

    while remain_left or remain_right:
        remain_left, remain_right = __clean_initial_separators(remain_left, remain_right)

        magic_old, remain_left, remain_right = __is_magically_old(remain_left, remain_right)
        if magic_old != 0:
            return magic_old
        if not remain_left or not remain_right:
            break
        left_numbers, remain_left = __get_numbers(remain_left)
        right_numbers, remain_right = __get_numbers(remain_right)
        if left_numbers or right_numbers:
            if not right_numbers:
                return 1  # left is newer, as numbers are newer than letters
            elif not left_numbers:
                return -1  # right is newer, as numbers are newer than letters
            else:
                numeric_result = __numeric_compare(left_numbers, right_numbers)
                if numeric_result != 0:
                    return numeric_result
        else:
            left_letters, remain_left = __get_letters(remain_left)
            right_letters, remain_right = __get_letters(remain_right)
            letter_result = __string_compare(left_letters, right_letters)
            if letter_result != 0:
                return letter_result
                    
    remain_left_len = len(remain_left)
    remain_right_len = len(remain_right)

    if remain_left_len > remain_right_len:
        return 1
    if remain_right_len > remain_left_len:
        return -1
    else:
        return 0


def __string_compare(left, right):
    if left > right:
        return 1
    elif right > left:
        return -1
    else:
        return 0


def __numeric_compare(left, right):
    left_trimmed = left.lstrip("0")
    right_trimmed = right.lstrip("0")

    left_len = len(left_trimmed)
    right_len = len(right_trimmed)

    if left_len > right_len:
        return 1
    elif right_len > left_len:
        return -1

    return __string_compare(left_trimmed, right_trimmed)


def __get_letters(version):
    matcher = LETTERS.match(version)
    if matcher:
        return matcher.group(1), matcher.group(2)
    else:
        return "", version


def __get_numbers(version):
    matcher = NUMBERS.match(version)
    if matcher:
        return matcher.group(1), matcher.group(2)
    else:
        return "", version


def __clean_initial_separators(remain_left, remain_right):
    remain_left = VERSION_SEPARATOR.sub("", remain_left, 1)
    remain_right = VERSION_SEPARATOR.sub("", remain_right, 1)
    return remain_left, remain_right


def __is_magically_old(left, right):
    """
    tilde has a special meaning, if both sections start with tilde, ignore it, if only one of them does, that one
    is considered older. This methods does both things

    :param left: one of the versions
    :param right: the other version
    :return: tuple (comparison result, left without tilde, right without tilde)
    """
    if left.startswith("~"):
        if right.startswith("~"):
            return 0, left[1:], right[1:]  # both start with ~, discard and compare section
        else:
            return -1, left[1:], right  # left is older
    elif right.startswith("~"):
        return 1, left, right[1:]  # right is older
    else:
        return 0, left, right
