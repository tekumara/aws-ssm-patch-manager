
import copy
import re
import logging
from patch_common.expression_tree import ExpressionTree as ET
from patch_common import rpm_version
from patch_common import package_matcher
logger = logging.getLogger()

class PackageRangeComparer():
    """
    This class is for taking a package range as a string. Eg.

        'kernel-default > 2.3.1-2.2.2'
        'rpm* < 2.* > 1.1.1-2.3.1'
        'curl*.x86_64 = 2.3.1-1.1.1' 
    
    And making it easily actionalable (ie, making it easy to send a package
    in to determine if it meets the requirement.)
    """
    def __init__(self, pkg_range_string, operator_functions = {}):
        """
        Constructor for the PackageRangeComparer
        :param pkg_range_string is the range string we are doing comparison on. 
            e.g.  'kernel-default > 2.3.1-2.2.2'
        :param operator_functions is a hash with the key as an operator string to expect
        and the value as the function that should be used for doing comparisons for that operator. 
        If not operator_functions are provided there is default functionality supported as 
        seen below.
        """
        self.operator_functions = operator_functions
        if not self.operator_functions or len(self.operator_functions) == 0:
            # default operators
            self.operator_functions = { 
                 "=": lambda l, r: rpm_version.compare(l, r) == 0,
                 "!=": lambda l, r: rpm_version.compare(l, r) != 0,
                 "<": lambda l, r: rpm_version.compare(l, r) < 0,
                 ">": lambda l, r: rpm_version.compare(l, r) > 0
                }
        
        self.name_tree = None
        self.version_trees = []
        self.__construct_trees(pkg_range_string)

    def matches_package(self, package):
        """
        Checks to see if the provided package matches this package range.
        :param - is a package object in tuple form (n, a, e, v, r)
        :returns True if package matches and false otherwise.
        """
        # ['kernel-default.x86_64', 'kernel-default']
        name_data = package_matcher.generate_package_data((package[0], package[1]), ['n', 'na'])
        return self.name_tree.execute(name_data) and \
            self.__match_version_trees(package)

    def __construct_trees(self, pkg_range_string):
        """
        Method for constructing the binary expression trees from a package range object. 
        :param - pkg_range_string to split into a binary expression tree.
        e.g.
            'kernel-default > 2.3.1-2.2.2'
            'rpm* < 2.* > 1.1.1-2.3.1'
            'curl*.x86_64 = 2.3.1-1.1.1' 
        :return - a list of expression trees representing the package range string.
        """
        operator_regex = "(%s)"%("|".join(self.operator_functions.keys()))
        
        #["kernel",">","3.4.5-2.2.2","<","4.4.4-1.1.1"]
        split_pkg_range_string = [x.strip() for x in re.split(operator_regex, pkg_range_string)]

        # grab name tree
        self.name_tree = ET("==")
        if "*" in split_pkg_range_string[0]:
            # The * glob universally represents "all" but it is not an accepted regex character. 
            # Translating the glob character "*" to a regex equivalent. 
            split_pkg_range_string[0] = split_pkg_range_string[0].replace("*", "(.)+")

        self.name_tree.right = re.compile(split_pkg_range_string[0])
        self.name_tree.operator_function = self.__name_equality_operator

        tree = None
        for item in split_pkg_range_string[1:]:
            if not tree:
                tree = ET(item)
            else:
                tree.right = item
                tree.operator_function = self.operator_functions[tree.operator]
                self.version_trees.append(tree)
                tree = None

    def __match_version_trees(self, package):
        """
        Method for determining if the provided package matches the version trees of this package_range_comparer.
        :param - package is an object with attributes name, arch, epoch, version and release (standards for Patch Manager
                 python objects)
        """
        for tree in self.version_trees:
            # ['4.1.45']
            version_data = package_matcher.generate_package_data((package[0], package[1], package[2], package[3], package[4]), ['vr'])
            if not tree.execute(version_data):
                return False
        return True

    def __name_equality_operator(self, left, right):
        """
        Method for evaluating a "name" expression tree. 
        :param - left is a string to compare.
        :param - right is a compile regex object (https://docs.python.org/3/library/re.html)
        :return - True if matches, False if not.
        """
        if right.match(left):
            return True
        return False

    # For debugging
    # def printTree(self, tree):
    #     logger.info(tree.left)
    #     logger.info(tree.operator)
    #     logger.info(tree.right)

    # def printTrees(self):
    #     self.printTree(self.name_tree)
    #     for tree in self.version_trees:
    #         self.printTree(tree)
