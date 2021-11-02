# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import os
import shutil

logger = logging.getLogger()


def remove_file(file_path):
    """
    Removes the file.
    :param file_path: to remove
    :return: None
    """
    os.remove(file_path)


def write_to_file(file_path, file_content):
    """
    Writes content to the file path.
    :param file_path: to write content.
    :param file_content: to write.
    :return:
    """
    with open(file_path, 'w') as file_path_handle:
        file_path_handle.write(file_content)


def create_directory(directory):
    """
    Creates a directory if it does not exist.
    :param directory: to create.
    :return: None
    """
    if not os.path.exists(directory):
        os.makedirs(directory)


def move_files_in_directory(from_directory, to_directory):
    """
    Moves all files in directory to another directory.
    :param from_directory: to move file from.
    :param to_directory: to move files to.
    :return: None
    """
    files = os.listdir(from_directory)

    for directory_file in files:
        logger.info("Moving %s to %s", directory_file, to_directory)

        from_file_path = os.path.join(from_directory, directory_file)
        to_file_path = os.path.join(to_directory, directory_file)

        shutil.move(from_file_path, to_file_path)


def move_file_path(from_file_path, to_file_path):
    """
    Moves a file from a location to another.
    :param from_file_path: of the file to move.
    :param to_file_path: for the file.
    :return: None
    """
    shutil.move(from_file_path, to_file_path)


def remove_directory(file_path):
    """
    Removes a directory if empty.
    :param file_path: to remove.
    :return: None
    """
    os.rmdir(file_path)


def get_file_last_modification_time(file_path):
    """
    Return file's last modification time if file exists
    :param file_path: local file path to check
    :return: the last modification time for the given path, or None if the file doesn't exist
    """
    if os.path.exists(file_path):
        return os.stat(file_path).st_mtime