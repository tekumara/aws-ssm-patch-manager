import logging
import yum_update_notice

logger = logging.getLogger()

class YumRequire:
    def __init__(self, require, yum_base):
        self.requirements = require
        self.yum_base = yum_base

    @property
    def installed(self):
        return is_pkg_installed(self.yum_base, *self.requirements)

    @property
    def provides(self):
        """
        A dictionary of package to a list of provides that satisfy the queried requirements
        """
        return self.yum_base.pkgSack.getProvides(*self.requirements)

    def match_baseline(self, baseline):
        """
        Determine if the requirements can be met by a package that satisfies baseline.
        :return: True if at least one provide for the requirements satisfies baseline.
        """
        # For requires with baselines, only need to check if it is rejected while blocking rejects is selected
        if baseline.has_rejected_patches and baseline.block_rejected_patches:
            provides = self.provides
            # When provides is empty, this YumRequire does not match_baseline
            for pkg in provides:
                # no need to check provides installation, we should check require installation before checking all its provides

                # As a dependency, we only need to check if it is in the rejected list
                if not yum_update_notice.match_yum_package(baseline.exclude, pkg.pkgtup):
                    return True

            logger.warn("All provides for require %s are rejected or no eligible provide.", self.requirements)
            return False

        # TODO add satisfied provides to the update list rather than depending on YUM to exclude rejected provides out? - 06/04/18 ouyangx@
        return True

    def match_override_list(self, override_list):
        if override_list is not None:
            provides = self.provides
            in_list_provides = []

            for pkg in provides:
                # no need to check provides installation, we should check require installation before checking all its provides

                if yum_update_notice.match_yum_package(override_list.id_filters, pkg.pkgtup):
                    in_list_provides.append(pkg)

            if len(in_list_provides) > 0:
                for pkg in in_list_provides:
                    if yum_update_notice.match_yum_package(override_list.all_filters, pkg.pkgtup):
                        # when any provide is in the list and found a match with the list, it will be installed/updated by matching the list
                        return True

                # when the package is in the list but no any suitable version from the provides, fail the dependency check
                logger.warn("Require %s is mentioned in the override list but no matching version.", self.requirements)
                return False

        # if no override list or no provides mentioned in the list, it means that no version requirements to the pkg
        return True

def is_pkg_installed(yum_base, name, flag=None, (epoch, version, release)=(None, None, None)):
    """
    Check whether a package is installed or not

    :param yum_base: YumBase from yum
    :param name: package name
    :param flag: flag to compare with
    :param (epoch, version, release): evr of the package
    :return: boolean to indicate whether it is installed or not
    """
    installed_pkg = yum_base.rpmdb.getProvides(name, flag, (epoch, version, release))
    if installed_pkg is not None and len(installed_pkg) > 0:
        return True
    return False


def check_require(yum_require, baseline, override_list=None):
    # if required dependency already installed, the requirements already met
    if yum_require.installed:
        return True

    # if require is not installed, need to check all provides
    if override_list is not None:
        return yum_require.match_override_list(override_list)
    else:
        return yum_require.match_baseline(baseline)

def check_all_requires(yum_base, yum_pkg, baseline, override_list):
    """
    Check all requires for a package

    :param yum_base: YumBase form yum
    :param yum_pkg: YumPackage object
    :param baseline: baseline to approve patches
    :param override_list: a list of patches to override installation decisions
    :return: boolean to indicate if it pass the check
    """
    if override_list is not None or (baseline.has_rejected_patches and baseline.block_rejected_patches):
        failed_requires = []

        if yum_pkg.pkg_obj is None:
            yum_pkg.set_package_object(yum_base)

        # No need to check the dependency if no override list or (no rejected patches or not blocking rejected patches)
        if yum_pkg.pkg_obj is None or yum_pkg.pkg_obj.requires is None:
            return True

        # Get and log all requires that fail the check once so that we can know all of them with one operation
        for require in yum_pkg.pkg_obj.requires:

            yum_require = YumRequire(require, yum_base)
            if not check_require(yum_require, baseline, override_list):
                failed_requires.append(require)

        if len(failed_requires) > 0:
            logger.warn("Failed requires check for pkgtup %s with the following requires: %s", yum_pkg.naevr, failed_requires)
            return False

    # No need to check the dependency if no override list or (no rejected patches or not blocking rejected patches)
    return True
