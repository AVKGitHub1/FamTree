# FamTree Design Doc

Docker hosted website for a family tree.

## Docker Details

### Hosting

The container should host a website at an otherwise unused and likely to be unused port.

### Security

Upon first launch, the container should print out an admin password.

The admin should have the ability to manage user codes for the website, such as generate a new code, view all codes and delete old codes.

An admin should have view and edit access to everything in the website.

A user with the correct code should have access as defined by the permissions granted to that code.

A user without a code (AKA a guest user) should only have view access to public info.

### Data

The data for this container should be stored under ```~/data/FamTree``` and should be sufficiently encrypted.

## Family Tree

### Node

Each node of this tree represents a person. Each person has some attributes. These attributes are required:

- Name
- Either a parent or a child or a spouse

While ading a new person, the user should add the name and then add the parent or the child or the spouse. While typing the name of the parent/child the user should have a dropdown list of matching names. If a matching name is found and the users chooses that name then the corresponding person's nodes should be updated to add the new person as either the child or the parent. The parent attribute should be split into mother/father.

Each person can have connections. Parents, siblings, children, spouses.

Each person can have multiple attributes. Common attributes are birthdate (allow for no birthyear), location, profession, short description. Th user should be allowed to add in custom attributes and then these attributes should be available for any future person node.

Each attribute can either be public or private. One connection (parent, spouse, child) needs to be public so that the person can be placed correctly in the tree.

### Connections

Each node should be connected to the parent(s), children, spouses. Allow for multiple spouses and multiples mathers/fathers.

### View

The family tree is organized by generation so that the parents sit at the top followed by children. Spouses and siblings should be on the same level.

Each node shoud appear as a rectangle with rounded corners. Connections should appear as lines connecting the nodes. Spouses should have lines connecting between them. If this couple has children, then a line should extend from the center of the spouse connection line and then branch out at right angles for the child/children. If a child has only 1 parent then the parent should have a line coming from the center horizontally then turn downwards at right angle and then be branched for the child/children.

The user should start off by seeing the full tree. The user should have four buttons on the side. These buttons (^+, ^-, ⌄+, ⌄-) should allow the user to show/hide the generations after clicking on a persons.

The user should have a button at the top that says Calculate Relation. Upon clicking that button, the user should be prompted to click two person nodes. The relation between the two nodes in cousin notation should be calculated and shown (such as first cousin, second cousin, first cousin twice removed, etc.).

Upon clicking a node, the user should have some available actions by the three vertical ⋮ menu of that node card.

### Available actions

Each action can either be private or public. The actions are:

- Add connection (private).
- Calculate relation with another card (public). This should work similar to the Calculate Relation button and should be the same as the user having clicked the Calculate Relation button and their first choice being the node from which this action is launched.

### Export

The family tree view (public/private depending on user) should be exportable as an image or pdf. The user should be asked what all attributes for all nodes they want saved (one connection attribute needs to be picked to ensure placement in the tree).

