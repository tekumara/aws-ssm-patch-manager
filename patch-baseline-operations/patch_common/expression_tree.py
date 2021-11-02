class ExpressionTree(): 
    """
    Class for representing package comparison's as an expression tree. 
    A compiled tree should look like this: 
    e.g.       > 
           //     \\
        None    3.8.5-2.1.1
    """
    # Constructor to create a node 
    def __init__(self, operator, operator_function = None): 
        """
        Constructor for expression tree. 
        :param operator is the operator (as a string) to execute on (this can be anything).
        This is mostly just for logging purposes.
        :param operator_function is the evaluation function to determine if the provided object
         satisfies the expression.
        """
        self.operator = operator
        self.left = None
        self.right = None
        self.operator_function = operator_function
    
    def execute(self, data_combos):
        """
        Method for checking if any of the provided data combinations pass the tree 
        evaluation. 
        :param data_combos - is a list of data combo's for this particular tree. 
        e.g. ["kernel-default", "kernel-default.x86_64"] for a name tree.
             or 
             ["4.5.1-2.3.1", "4.5.1"] for a version tree. 
        """
        match_found = False
        for item in data_combos:
            (left, right) = self.__prepare_for_comparison(item)
            if self.operator_function(left, right) == True:
                return True
        return False

    def __prepare_for_comparison(self, left):
        """
        Method for handling version comparison with glob.
        :param left - is the incoming data object to compare to the tree. e.g '4.3.2-1.1.1'
        More info: 
        If the expression tree looks like this: 
                        > 
                    //     \\
                None        3.*
        
        rpm version comaprison doesn't understand it so the following comparison will fail.
                          
                          > 
                    //          \\
                4.5.2-2.1.1      3.*

        We simply strip the incoming data object to look like this: 
                           > 
                    //          \\
                    4.            3.

        Since it is equivalent and * will only be present for version comparisons.
        """
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