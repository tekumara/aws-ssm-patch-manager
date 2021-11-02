# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
import yum_base
from sys import stderr


def yum_list_repos(baseline):
    """
    :param baseline: yum_baseline.YumBaseline
    :return: a list of YumRepository objects
    """
    yb = yum_base.setup_yum_base(baseline)
    return yb.repos.listEnabled()


def yum_detect_repo_change(original_repos, post_install_repos):
    """
    Compares enabled yum repositories and checks for differences are installing updates
    :param original_repos: yum.yumRepo.YumRepository
    :type post_install_repos: yum.yumRepo.YumRepository
    :return true if any repo has changed, false otherwise
    """
    return sorted(original_repos) != sorted(post_install_repos)


def log_repo_update_error():
    """
    Log error for when repositories change during update process
    """
    stderr.write("REPOSITORY_UPDATE_ERROR: A repository change occurred during installation and there are new updates "
                 "available. Please re-run the AWS-RunPatchBaseline document in order to apply the latest updates.\n")
