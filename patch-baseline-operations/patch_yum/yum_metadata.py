# Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import yum
# Certain versions of CentOS do not recognize this module without the explicit import. Do not remove.
# For more info please see: https://code.amazon.com/reviews/CR-1667249/revisions/1#/details
import yum.update_md
import yum_package


def get_available_pkgs(yb):
    """
    All packages yum knows about

    :param yb: yum base from yum 
    :return: a set of YumPackage Objects
    """
    pkgs = set()
    for pkg in sorted(yb.pkgSack.returnPackages()):
        pkgs.add(yum_package.YumPackage((pkg.name, pkg.arch, pkg.epoch, pkg.version, pkg.release), buildtime=pkg.buildtime))

    return pkgs


def get_update_metadata(repos):
    """
    Get the update metadata for the requested repos.

    :param repos: usually yb.repos.listEnabled()
    :return: update metadata which containing update notices
    """
    update_metadata = yum.update_md.UpdateMetadata()
    for repo in repos:
        if not repo.enabled:
            continue
        try:  # attempt to grab the updateinfo.xml.gz from the repodata
            update_metadata.add(repo)
        except yum.Errors.RepoMDError:
            continue  # No metadata found for this repo

    # TODO add filter on metadata for approve after days, etc
    return update_metadata
