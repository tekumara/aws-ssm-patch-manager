
import copy
import re
import package_matcher
import logging
import rpm_version

logger = logging.getLogger()
# Python program for expression tree 
#   https://en.opensuse.org/openSUSE:Libzypp_locks_file
# exact,substring,regex,glob and word
# An expression tree node 
class ExpressionTree(): 

    # Constructor to create a node 
    def __init__(self, operator, operator_function = None): 
        self.operator = operator
        self.left = None
        self.right = None
        self.operator_function = operator_function
    
    def execute(self, data_combos):
        for item in data_combos:
            (left, right) = self.prepare_for_comparison(item)
            if self.operator_function(left, right) == True:
                return True
        
        return False

    def prepare_for_comparison(self, left):
        if not isinstance(self.right, str):
            return (left, self.right)

        if "*" in self.right:
            index = self.right.find("*")
            right = self.right[0:index]
            if len(left) > len(right):
                left = left[0:index]
            return (left, right)
        else:
            return (left, self.right)

class ZypperLockComparer():

    def __init__(self, pkg_range_string, operator_functions = {}):
        if not operator_functions or len(operator_functions) == 0:
            # default operators
            self.operator_functions = { 
                "==": self.eq,
                "<=": self.le,
                ">=": self.ge,
                "!=": self.ne,
                "<": self.lt,
                ">": self.gt} 
        
        self.name_tree = None
        self.version_trees = []
        self.constructTrees(pkg_range_string)
 
    def constructTrees(self, pkg_range_string):
        operator_regex = "(%s)"%("|".join(self.operator_functions.keys()))
        split = [x.strip() for x in re.split(operator_regex, pkg_range_string)]

        # grab name tree
        self.name_tree = ET("==")
        self.name_tree.right = re.compile(split[0])
        self.name_tree.operator_function = self.name_equality_operator
        del split[0]

        tree = None
        for item in split:
            if not tree:
                tree = ET(item)
            else:
                tree.right = item
                tree.operator_function = self.operator_functions[tree.operator]
                self.version_trees.append(tree)
                tree = None
    
    def match_version_trees(self, version_data):
        for tree in self.version_trees:
            if not tree.execute(version_data):
                return False
        return True

    def matches_package(self, package):
        """
        Example for package: 
        package = Package(name = "kernel-default", arch="x86_64", epoch="0", version="4.1.45", release="3.4.5")
        ['kernel-default.x86_64', 'kernel-default']
        ['4.1.45-3.4.5', '4.1.45']
        """
        # ['kernel-default.x86_64', 'kernel-default']
        name_data = package_matcher.generate_package_data((package.name, package.arch), ['n', 'na'])
        # ['4.1.45-3.4.5', '4.1.45']
        version_data = package_matcher.generate_package_data((package.name, package.arch, package.epoch, package.version, package.release), ['vr', 'v'])

        return self.name_tree.execute(name_data) and \
            self.match_version_trees(version_data)

    def name_equality_operator(self, left, right):
        # This is the only one that compiles the regex.
        if right.match(left):
            return True
        return False

    # rpm_version.compare returns the following values: 
    # return 1 if left is newer, 0 if equal, -1 if right is newer
    def lt(self, left, right):
        if (rpm_version.compare(left, right) in [-1]):
            return True
        
        return False

    def gt(self, left, right):
        if (rpm_version.compare(left, right) in [1]):
            return True
        
        return False

    def eq(self, left, right):
        if (rpm_version.compare(left, right) in [0]):
            return True
        
        return False 

    def le(self, left, right):
        if (rpm_version.compare(left, right) in [-1, 0]):
            return True
        
        return False 

    def ge(self, left, right):
        if (rpm_version.compare(left, right) in [0, 1]):
            return True
        
        return False 

    def ne(self, left, right):
        if (rpm_version.compare(left, right) in [-1, 1]):
            return True
        
        return False 

    # def printTree(self, tree):
    #     print(tree.left)
    #     print(tree.operator)
    #     print(tree.right)

    # def printTrees(self):
    #     self.printTree(self.name_tree)
    #     for tree in self.version_trees:
    #         self.printTree(tree)

  

