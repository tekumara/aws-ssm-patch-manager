from patch_common.package_matcher import generate_package_data, APT_CODES
from patch_apt.constants import ChangeType


class Change:
    def __init__(self, apt_package, candidate_version=None, change_type=None, problem=None):
        """
        An object can be used to store the usable candidate or problem of a package change:
            1) upgrading a package e.g. A could also package changes for other packages, e.g. B, C, D, this can be used
            to store any package exists a problem, e.g. B could be broken, C needs to be installed but it is rejected
            2) when try to resolve the issues of upgrading a package, e.g. A, some packages needs to be adjusted to a
            specific version, otherwise, a problem could be detected, e.g. B needs to be adjusted from v3 to v2,
            otherwise, it will be removed as well as its parents. This can also be used to store the required candidate
        :param apt_package: apt Package object
        :param candidate_version: the current candidate version to be remembered.
            because the candidate object of apt package could be changed when manipulating apt cache
        :param change_type: one of ChangeType to indicate the package change, e.g. INSTALL
        :param problem: one of ProblemType to indicate the problem of this package could have,
                        and the problem could be different when the main package that triggered the change is different
        """
        self.apt_package = apt_package
        self._problem = problem

        # Add specific properties in case the following version and change type changed when manipulating cache
        self.installed_version = apt_package.installed if apt_package.is_installed else None
        self.candidate_version = candidate_version or apt_package.candidate
        self.change_type = change_type or self.get_change_type(apt_package)


    @staticmethod
    def get_change_type(apt_package):
        """
        Get change type of an apt package according to its marking status, e.g. INSTALL
        :param apt_package: apt Package object
        :return: change type as a string
        """
        if apt_package.marked_install:
            return ChangeType.INSTALL
        if apt_package.marked_upgrade:
            return ChangeType.UPGRADE
        if apt_package.marked_delete:
            return ChangeType.DELETE
        if apt_package.marked_keep:
            return ChangeType.KEEP
        if apt_package.marked_downgrade:
            return ChangeType.DOWNGRADE
        if apt_package.marked_reinstall:
            return ChangeType.REINSTALL
        if apt_package.is_now_broken or apt_package.is_inst_broken:
            return ChangeType.BROKEN

    @property
    def name(self):
        return self.apt_package.name

    @property
    def problem(self):
        """Get the problem"""
        return self._problem

    def set_problem(self, problem):
        """Set the problem to the given one"""
        self._problem = problem

    def set_candidate(self, candidate_version=None):
        """
        Set the candidate for the apt package, can be used to set the correct candidate for required changes
        :param candidate_version: Version object of an APT package
        :return:
        """
        candidate = candidate_version or self.candidate_version
        self.apt_package.candidate = candidate


    def get_other_applicable_versions(self):
        """
        Get other applicable versions of the change, can be used when need to adjust the candidate to resolve issues.
        Right now, we only try to resolve broken packages that could be deleted, which is DELETE_BROKEN
        All potential broken packages should be installed and the current installed version triggered the issue,
        also, we ONLY upgrade packages and we should not try to downgrade any packages,
        hence, we need to get all versions that are higher than the installed versions
        :return: a list of sorted (higher than installed) versions from higher to lower
        """
        pkg_versions = [ pkg_ver for pkg_ver in self.apt_package.versions
                 if self.apt_package.is_installed
                 and pkg_ver._cmp(self.apt_package.installed) > 0
                 and pkg_ver.version != self.candidate_version.version ]
        return sorted(pkg_versions, key=lambda x: x.version, reverse=True)


